import argparse
import base64
import configparser
import io
import json
import os
import threading
import time
import uuid
from pathlib import Path

from PIL import Image

from app.paths import PROJECT_ROOT, config_file, data_dir, logs_dir
from core.analyzer import analyze_text, get_analysis_mode, get_default_model
from core.app_detector import (
    capture_active_window,
    download_url_for_app,
    enrich_monitored_apps,
    get_active_window_info,
    normalize_app_name,
    open_download_for_app,
)
from core.benchmark import build_comparison, summarize_model_result
from core.dashboard_bridge import read_state, write_command
from core.experimental.datasets import parse_dataset_content
from core.experimental.ocr_benchmark import run_ocr_benchmark_from_content, run_ocr_pipeline_benchmark
from core.experimental.runner import resume_batch_experiment, run_batch_experiment, run_robustness_experiment
from core.experimental.store import (
    experimental_summary,
    export_experiment,
    generate_experiment_report,
    get_experiment,
    init_experimental_db,
    list_experiment_metrics,
    list_experiment_results,
    save_dataset,
)
from core.experimental.threshold_calibration import calibrate_thresholds
from core.history_store import (
    add_event,
    add_monitored_app,
    clear_history,
    delete_analysis,
    export_history,
    get_stats,
    list_analyses,
    list_events,
    list_monitored_apps,
    mark_analysis_feedback,
    remove_custom_app,
    save_analysis,
    set_app_enabled,
    validate_analysis,
)
from core.ocr import extract_text, get_ocr_language, get_tesseract_cmd
from core.ollama_manager import check_ollama_running, get_installed_models
from core.api_key_manager import has_api_key, save_api_key
from core.qr_analyzer import analyze_qr_codes, apply_qr_analysis_to_result, build_qr_analysis_text
from core.system_diagnostics import run_system_diagnostics


BASE_DIR = PROJECT_ROOT
CONFIG_PATH = config_file()

class ReportApi:
    __slots__ = ("report_path",)

    def __init__(self, report_path=None):
        self.report_path = report_path

    def getReportData(self):
        if not self.report_path or not os.path.exists(self.report_path):
            return {}
        with open(self.report_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def closeWindow(self):
        import webview

        if webview.windows:
            webview.windows[0].destroy()

    def completeLoading(self):
        self.closeWindow()


class CyberDetectApi(ReportApi):
    __slots__ = (
        "report_path",
        "_models_cache",
        "_models_cache_at",
        "_models_refreshing",
        "_ollama_running",
        "_experiment_cancellations",
    )

    def __init__(self, report_path=None):
        super().__init__(report_path)
        self._models_cache = []
        self._models_cache_at = 0.0
        self._models_refreshing = False
        self._ollama_running = False
        self._experiment_cancellations = {}
        init_experimental_db()
        self._refresh_models_background()

    def getDashboardData(self):
        return {
            "stats": get_stats(),
            "analyses": list_analyses(limit=80),
            "events": list_events(limit=80),
            "apps": self._apps(),
            "models": self._models(),
            "settings": self._settings(),
            "logs": self._logs(),
            "system": self._system(),
            "experimental": self._experimental(),
        }

    def analyzeText(self, text):
        clean = str(text or "").strip()
        if not clean:
            return {"ok": False, "error": "Informe um texto para analisar."}
        result, metadata = analyze_text(clean, get_default_model())
        save_analysis(result, metadata, source="manual", input_text=clean)
        add_event("analysis", f"Analise manual pelo painel React: {result.get('classificacao')}", "INFO", metadata)
        return {"ok": True, "result": result, "metadata": metadata}

    def analyzeImageData(self, data_url, filename="imagem"):
        try:
            payload = str(data_url or "")
            if "," in payload:
                payload = payload.split(",", 1)[1]
            image_bytes = base64.b64decode(payload)
            image = Image.open(io.BytesIO(image_bytes))
            extracted_text = extract_text(image)
            qr_analysis = analyze_qr_codes(image)
            analysis_text = build_qr_analysis_text(extracted_text, qr_analysis)
            if not analysis_text.strip():
                add_event("ocr", f"OCR/QR sem conteudo extraido de {filename}", "WARN", {"qr": qr_analysis})
                return {"ok": False, "error": "OCR nao encontrou texto legivel e nenhum QR Code foi detectado na imagem."}

            result, metadata = analyze_text(analysis_text, get_default_model())
            result = apply_qr_analysis_to_result(result, qr_analysis, analysis_text)
            metadata = {
                **metadata,
                "filename": str(filename or "imagem"),
                "qr_detected": len(qr_analysis.get("items") or []),
                "qr_detector_available": bool(qr_analysis.get("available")),
                "qr_detector_error": qr_analysis.get("error") or "",
            }
            save_analysis(result, metadata, source="image", input_text=analysis_text)
            add_event("ocr", f"Imagem analisada pelo painel React: {filename}", "INFO", metadata)
            return {
                "ok": True,
                "result": result,
                "metadata": metadata,
                "extracted_text": extracted_text,
                "analysis_text": analysis_text,
                "qr_analysis": qr_analysis,
            }
        except Exception as exc:
            add_event("ocr", f"Falha ao analisar imagem: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def runBenchmark(self, text, models):
        clean = str(text or "").strip()
        selected = [str(model) for model in (models or []) if str(model).strip()][:3]
        if not clean:
            return {"ok": False, "error": "Informe um texto para benchmark."}
        if not selected:
            return {"ok": False, "error": "Selecione ao menos um modelo."}

        results = []
        for model in selected:
            try:
                result, metadata = analyze_text(clean, model)
                error = metadata.get("erro") or ""
            except Exception as exc:
                result = {
                    "classificacao": "ERRO",
                    "score_risco": 0,
                    "resumo": f"Falha ao executar {model}.",
                    "recomendacao": "Verifique se o modelo esta instalado e tente novamente.",
                    "pontos_suspeitos": [],
                    "tecnicas_engenharia_social": [],
                }
                metadata = {
                    "modelo": model,
                    "tempo_resposta_ms": 0,
                    "json_valido": False,
                    "erro": str(exc),
                }
                error = str(exc)
            item = summarize_model_result(model, result, metadata, "", error)
            results.append({key: value for key, value in item.items() if not key.startswith("_")})
            save_analysis(result, metadata, source="benchmark", input_text=clean)

        comparison = build_comparison(results)
        add_event("benchmark", f"Benchmark pelo painel React: {comparison.get('consenso', '-')}", "INFO", comparison)
        return {"ok": True, "results": results, "comparison": comparison}

    def requestScreenAnalysis(self):
        command = write_command("run_screen_analysis")
        add_event("dashboard", "Solicitada analise de tela pelo painel React", "INFO", command)
        self._hide_window_until_capture_finishes(command.get("id"))
        return {"ok": True, "command": command}

    def _hide_window_until_capture_finishes(self, command_id):
        if not command_id:
            return

        try:
            import webview

            window = webview.windows[0] if webview.windows else None
        except Exception:
            window = None

        if not window:
            return

        try:
            if hasattr(window, "minimize"):
                window.minimize()
            elif hasattr(window, "hide"):
                window.hide()
        except Exception as exc:
            add_event("dashboard", f"Nao foi possivel minimizar painel para captura: {exc}", "WARN")

        def restore_when_done():
            deadline = time.time() + 90
            while time.time() < deadline:
                state = read_state()
                if state.get("last_capture_finished_id") == command_id:
                    break
                time.sleep(0.25)
            time.sleep(0.25)
            try:
                if hasattr(window, "restore"):
                    window.restore()
                elif hasattr(window, "show"):
                    window.show()
            except Exception as exc:
                add_event("dashboard", f"Nao foi possivel restaurar painel apos captura: {exc}", "WARN")

        threading.Thread(target=restore_when_done, daemon=True).start()

    def setProtection(self, interval):
        try:
            seconds = max(0, int(interval or 0))
        except (TypeError, ValueError):
            seconds = 0
        command = write_command("set_auto_interval", {"interval": seconds})
        add_event("protection", f"Solicitada protecao ativa: {seconds}s", "INFO", command)
        return {"ok": True, "command": command}

    def setAppEnabled(self, app_id, enabled):
        apps = self._apps()
        target = next((app for app in apps if int(app.get("id", 0)) == int(app_id)), None)
        if target and not target.get("can_monitor", True):
            return {
                "ok": False,
                "error": "Aplicativo nao instalado nesta maquina.",
                "apps": apps,
            }
        ok = set_app_enabled(int(app_id), bool(enabled))
        return {"ok": ok, "apps": self._apps()}

    def addApp(self, name):
        ok = add_monitored_app(str(name or ""))
        return {"ok": ok, "apps": self._apps()}

    def removeApp(self, app_id):
        ok = remove_custom_app(int(app_id))
        return {"ok": ok, "apps": self._apps()}

    def openAppDownload(self, app_id):
        apps = self._apps()
        target = next((app for app in apps if int(app.get("id", 0)) == int(app_id)), None)
        if not target:
            return {"ok": False, "error": "Aplicativo nao encontrado.", "apps": apps}

        url = download_url_for_app(str(target.get("name", "")))
        if not url:
            return {"ok": False, "error": "Download indisponivel para este app.", "apps": apps}

        open_download_for_app(str(target.get("name", "")))
        add_event("monitoring", f"Download oficial aberto: {target.get('name')}", "INFO", {"url": url})
        return {"ok": True, "url": url, "apps": self._apps()}

    def testMonitoring(self):
        window = self._minimize_dashboard_window()
        try:
            time.sleep(0.45 if window else 0.05)
            image, active = capture_active_window()
            if not active:
                active = get_active_window_info()

            apps = self._apps()
            monitored_match = self._match_monitored_app(active, apps)
            capture_ok = image is not None
            ocr_text = ""
            ocr_status = "FALHA"
            if image is not None:
                try:
                    ocr_text = extract_text(image)
                    ocr_status = "OK" if ocr_text.strip() else "SEM TEXTO"
                except Exception as exc:
                    ocr_status = "FALHA"
                    add_event("ocr", f"Falha no OCR do teste de monitoramento: {exc}", "ERROR")

            app_detected = active.get("app_name") or active.get("process_name") or "NAO IDENTIFICADO"
            trigger_ok = bool(monitored_match and capture_ok)
            if trigger_ok and ocr_status == "OK":
                status = "MONITORAMENTO FUNCIONANDO"
            elif trigger_ok:
                status = "CAPTURA OK / OCR SEM TEXTO"
            elif capture_ok:
                status = "APP FORA DA LISTA MONITORADA"
            else:
                status = "CAPTURA INDISPONIVEL"

            result = {
                "app_detectado": str(app_detected).upper(),
                "app_monitorado": str(monitored_match or "-").upper(),
                "janela": active.get("title") or "-",
                "processo": active.get("process_name") or "-",
                "captura": "OK" if capture_ok else "FALHA",
                "ocr": ocr_status,
                "trigger": "OK" if trigger_ok else "IGNORADO",
                "status": status,
                "ocr_preview": (ocr_text or "").strip()[:700],
            }
            add_event("monitoring", f"Teste de monitoramento: {status}", "INFO", result)
            return {"ok": True, "result": result, "apps": self._apps()}
        except Exception as exc:
            add_event("monitoring", f"Falha no teste de monitoramento: {exc}", "ERROR")
            return {"ok": False, "error": str(exc), "apps": self._apps()}
        finally:
            self._restore_dashboard_window(window)

    def deleteHistory(self, analysis_id):
        return {"ok": delete_analysis(int(analysis_id)), "analyses": list_analyses(limit=80)}

    def clearHistory(self):
        return {"ok": clear_history(), "analyses": []}

    def exportHistory(self, filetype):
        ext = "csv" if str(filetype).lower() == "csv" else "json"
        export_dir = data_dir()
        export_dir.mkdir(exist_ok=True)
        path = export_dir / f"cyberdetect_history_export_{int(time.time())}.{ext}"
        ok = export_history(str(path), ext)
        return {"ok": ok, "path": str(path)}

    def validateAnalysis(self, analysis_id, ground_truth, note="", source="manual"):
        ok = validate_analysis(
            int(analysis_id),
            str(ground_truth or ""),
            str(note or ""),
            str(source or "manual"),
        )
        return {"ok": ok, "analyses": list_analyses(limit=80)}

    def markAnalysisFeedback(self, analysis_id, is_correct, correct_class="", note=""):
        ok = mark_analysis_feedback(
            int(analysis_id),
            bool(is_correct),
            str(correct_class or ""),
            str(note or ""),
            "manual_feedback",
        )
        return {"ok": ok, "analyses": list_analyses(limit=80)}

    def importExperimentalDataset(self, filename, content, datasetName="", version="1.0", binary=False):
        try:
            samples, errors = parse_dataset_content(
                str(filename or "dataset.json"),
                str(content or ""),
                str(datasetName or ""),
                bool(binary),
            )
            if not samples:
                return {"ok": False, "error": "Nenhuma amostra valida encontrada.", "errors": errors[:20]}

            name = str(datasetName or "").strip() or Path(str(filename or "dataset")).stem or "dataset"
            saved = save_dataset(
                name=name,
                version=str(version or "1.0"),
                samples=samples,
                source_path=str(filename or ""),
                source_format=Path(str(filename or "")).suffix.lower().lstrip("."),
                metadata={"import_errors": errors[:100], "binary": bool(binary)},
            )
            add_event(
                "experimental",
                f"Dataset experimental importado: {name} ({len(samples)} amostras)",
                "INFO",
                {"dataset": saved, "errors": len(errors)},
            )
            return {"ok": True, "dataset": saved, "errors": errors[:20], "experimental": self._experimental()}
        except Exception as exc:
            add_event("experimental", f"Falha ao importar dataset: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def startExperimentalBatch(self, config):
        config = config or {}
        try:
            dataset_id = int(config.get("datasetId") or config.get("dataset_id") or 0)
            if dataset_id <= 0:
                return {"ok": False, "error": "Selecione um dataset experimental."}

            experiment_id = f"CD-EXP-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
            cancel_event = threading.Event()
            self._experiment_cancellations[experiment_id] = cancel_event

            def worker():
                try:
                    run_batch_experiment(
                        dataset_id=dataset_id,
                        models=[str(item) for item in config.get("models", [])],
                        approaches=[str(item) for item in config.get("approaches", ["hybrid"])],
                        sample_limit=int(config.get("sampleLimit") or config.get("sample_limit") or 0),
                        seed=int(config.get("seed")) if str(config.get("seed", "")).strip() else None,
                        category=str(config.get("category") or ""),
                        language=str(config.get("language") or ""),
                        cancel_event=cancel_event,
                        experiment_id=experiment_id,
                    )
                    add_event("experimental", f"Experimento finalizado: {experiment_id}", "INFO")
                except Exception as exc:
                    add_event("experimental", f"Experimento falhou: {experiment_id}: {exc}", "ERROR")
                finally:
                    self._experiment_cancellations.pop(experiment_id, None)

            threading.Thread(target=worker, daemon=True).start()
            add_event("experimental", f"Experimento iniciado: {experiment_id}", "INFO", config)
            return {"ok": True, "experimentId": experiment_id}
        except Exception as exc:
            add_event("experimental", f"Falha ao iniciar experimento: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def getExperimentalStatus(self, experiment_id=""):
        experiment = get_experiment(str(experiment_id or ""))
        if not experiment:
            return {"ok": False, "error": "Experimento nao encontrado."}
        return {
            "ok": True,
            "experiment": experiment,
            "metrics": list_experiment_metrics(experiment["id"]),
            "results": list_experiment_results(experiment["id"])[:80],
        }

    def cancelExperimentalBatch(self, experiment_id):
        event = self._experiment_cancellations.get(str(experiment_id or ""))
        if not event:
            return {"ok": False, "error": "Experimento nao esta em execucao."}
        event.set()
        add_event("experimental", f"Cancelamento solicitado: {experiment_id}", "WARN")
        return {"ok": True}

    def resumeExperimentalBatch(self, experiment_id):
        experiment_id = str(experiment_id or "")
        if not experiment_id:
            return {"ok": False, "error": "Experimento nao informado."}
        cancel_event = threading.Event()
        self._experiment_cancellations[experiment_id] = cancel_event

        def worker():
            try:
                resume_batch_experiment(experiment_id, cancel_event=cancel_event)
                add_event("experimental", f"Experimento retomado/finalizado: {experiment_id}", "INFO")
            except Exception as exc:
                add_event("experimental", f"Falha ao retomar experimento {experiment_id}: {exc}", "ERROR")
            finally:
                self._experiment_cancellations.pop(experiment_id, None)

        threading.Thread(target=worker, daemon=True).start()
        add_event("experimental", f"Retomada solicitada: {experiment_id}", "INFO")
        return {"ok": True, "experimentId": experiment_id}

    def startRobustnessExperiment(self, config):
        config = config or {}
        try:
            dataset_id = int(config.get("datasetId") or config.get("dataset_id") or 0)
            if dataset_id <= 0:
                return {"ok": False, "error": "Selecione um dataset experimental."}
            experiment_id = f"CD-ROB-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
            cancel_event = threading.Event()
            self._experiment_cancellations[experiment_id] = cancel_event

            def worker():
                try:
                    run_robustness_experiment(
                        dataset_id=dataset_id,
                        models=[str(item) for item in config.get("models", [])],
                        approaches=[str(item) for item in config.get("approaches", ["hybrid"])],
                        sample_limit=int(config.get("sampleLimit") or config.get("sample_limit") or 0),
                        seed=int(config.get("seed")) if str(config.get("seed", "")).strip() else None,
                        variant_limit=int(config.get("variantLimit") or config.get("variant_limit") or 10),
                        cancel_event=cancel_event,
                        experiment_id=experiment_id,
                    )
                    add_event("experimental", f"Robustez finalizada: {experiment_id}", "INFO")
                except Exception as exc:
                    add_event("experimental", f"Robustez falhou: {experiment_id}: {exc}", "ERROR")
                finally:
                    self._experiment_cancellations.pop(experiment_id, None)

            threading.Thread(target=worker, daemon=True).start()
            add_event("experimental", f"Robustez iniciada: {experiment_id}", "INFO", config)
            return {"ok": True, "experimentId": experiment_id}
        except Exception as exc:
            add_event("experimental", f"Falha ao iniciar robustez: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def exportExperiment(self, experiment_id, filetype="json"):
        try:
            path = export_experiment(str(experiment_id or ""), str(filetype or "json"))
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def generateExperimentReport(self, experiment_id):
        try:
            path = generate_experiment_report(str(experiment_id or ""))
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def runOcrBenchmark(self, filename, content):
        try:
            result = run_ocr_benchmark_from_content(str(filename or "ocr_dataset.json"), str(content or ""))
            add_event("experimental", f"OCR benchmark concluido: {filename}", "INFO", result)
            return {"ok": True, "result": result}
        except Exception as exc:
            add_event("experimental", f"OCR benchmark falhou: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def runOcrImageBenchmark(self, data_url, filename="imagem", expected_text=""):
        try:
            payload = str(data_url or "")
            if "," in payload:
                payload = payload.split(",", 1)[1]
            image_bytes = base64.b64decode(payload)
            image = Image.open(io.BytesIO(image_bytes))
            result = run_ocr_pipeline_benchmark(image, str(expected_text or ""), str(filename or "imagem"))
            add_event("experimental", f"OCR pipeline benchmark concluido: {filename}", "INFO", {
                "sample_count": result.get("sample_count"),
                "best_pipeline": result.get("best_pipeline"),
                "path": result.get("path"),
            })
            return {"ok": True, "result": result}
        except Exception as exc:
            add_event("experimental", f"OCR pipeline benchmark falhou: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def runThresholdCalibration(self, experiment_id="", thresholds=None):
        try:
            experiment_id = str(experiment_id or "")
            if not experiment_id:
                experiments = (experimental_summary() or {}).get("experiments") or []
                experiment_id = str((experiments[0] or {}).get("id") or "") if experiments else ""
            if not experiment_id:
                return {"ok": False, "error": "Nenhum experimento disponivel para calibracao."}

            parsed_thresholds = []
            for item in thresholds or []:
                try:
                    parsed_thresholds.append(int(float(item)))
                except (TypeError, ValueError):
                    continue

            rows = calibrate_thresholds(
                list_experiment_results(experiment_id),
                parsed_thresholds,
            )
            add_event(
                "experimental",
                f"Threshold calibration executada: {experiment_id}",
                "INFO",
                {"thresholds": parsed_thresholds, "rows": len(rows)},
            )
            return {"ok": True, "experimentId": experiment_id, "rows": rows}
        except Exception as exc:
            add_event("experimental", f"Threshold calibration falhou: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def runSystemDiagnostics(self, options=None):
        try:
            options = options or {}
            diagnostics = run_system_diagnostics(
                BASE_DIR,
                include_capture=bool(options.get("includeCapture", True)),
                include_external_api=bool(options.get("includeExternalApi", True)),
                include_ollama=bool(options.get("includeOllama", True)),
            )
            summary = diagnostics.get("summary") or {}
            add_event(
                "diagnostics",
                f"Autodiagnostico executado: {summary.get('status', 'WARN')}",
                "INFO",
                {"summary": summary},
            )
            return {"ok": True, "diagnostics": diagnostics}
        except Exception as exc:
            add_event("diagnostics", f"Autodiagnostico falhou: {exc}", "ERROR")
            return {"ok": False, "error": str(exc)}

    def saveSettings(self, settings):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH, encoding="utf-8")
        for section in ["Models", "Analysis", "ExternalAPI", "General", "Automation", "UI", "Logs", "History"]:
            if section not in config:
                config.add_section(section)

        settings = settings or {}
        def setting_value(key, section, option, fallback):
            value = settings.get(key)
            if value is None or value == "":
                return config.get(section, option, fallback=fallback)
            return value

        config["Models"]["default_model"] = str(setting_value("defaultModel", "Models", "default_model", "llama3.2:3b"))
        config["Analysis"]["default_mode"] = str(setting_value("analysisMode", "Analysis", "default_mode", "automatico"))
        config["ExternalAPI"]["provider"] = str(setting_value("provider", "ExternalAPI", "provider", "OpenAI"))
        config["ExternalAPI"]["external_model"] = str(setting_value("externalModel", "ExternalAPI", "external_model", "gpt-4o-mini"))
        config["General"]["ocr_language"] = str(setting_value("ocrLanguage", "General", "ocr_language", "por+eng"))
        config["Automation"]["cooldown_seconds"] = str(setting_value("cooldownSeconds", "Automation", "cooldown_seconds", "30"))
        config["Automation"]["smart_trigger"] = "true" if settings.get("smartTrigger", True) else "false"
        config["Automation"]["auto_protection"] = "true" if settings.get("autoProtection", False) else "false"
        config["Automation"]["sensitivity"] = str(setting_value("sensitivity", "Automation", "sensitivity", "70"))
        config["UI"]["theme"] = str(setting_value("theme", "UI", "theme", "system"))
        config["Logs"]["directory"] = str(setting_value("logsDirectory", "Logs", "directory", str(logs_dir())))
        config["History"]["retention_days"] = str(setting_value("retentionDays", "History", "retention_days", "180"))

        api_key = str(settings.get("apiKey") or "").strip()
        if api_key:
            save_api_key(api_key)

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
        add_event("settings", "Configuracoes salvas pelo painel React", "INFO")
        return {"ok": True, "settings": self._settings()}

    def _apps(self):
        return enrich_monitored_apps(list_monitored_apps())

    def _match_monitored_app(self, active, apps):
        app_key = active.get("app_key")
        process_app_key = active.get("process_app_key")
        title = normalize_app_name(active.get("title"))
        process_name = normalize_app_name(active.get("process_name"))

        for app in apps:
            if not app.get("enabled") or not app.get("can_monitor", True):
                continue
            if app.get("app_key") in {app_key, process_app_key}:
                return app.get("canonical_name") or app.get("name")
            if app.get("is_custom"):
                custom = normalize_app_name(app.get("name"))
                if custom and (custom in title or custom in process_name):
                    return app.get("name")
        return ""

    def _minimize_dashboard_window(self):
        try:
            import webview

            window = webview.windows[0] if webview.windows else None
        except Exception:
            window = None

        if not window:
            return None
        try:
            if hasattr(window, "minimize"):
                window.minimize()
            elif hasattr(window, "hide"):
                window.hide()
            return window
        except Exception as exc:
            add_event("dashboard", f"Nao foi possivel minimizar painel para teste: {exc}", "WARN")
            return None

    def _restore_dashboard_window(self, window):
        if not window:
            return
        try:
            if hasattr(window, "restore"):
                window.restore()
            elif hasattr(window, "show"):
                window.show()
        except Exception as exc:
            add_event("dashboard", f"Nao foi possivel restaurar painel apos teste: {exc}", "WARN")

    def _models(self):
        if time.time() - self._models_cache_at > 60:
            self._refresh_models_background()
        supported = ["gemma3:4b", "llama3.2:3b", "qwen2.5:3b", "phi4-mini:latest"]
        return {
            "installed": self._models_cache,
            "supported": supported,
            "ollamaRunning": self._ollama_running,
        }

    def _refresh_models_background(self):
        if self._models_refreshing:
            return
        self._models_refreshing = True

        def worker():
            try:
                self._ollama_running = check_ollama_running()
                self._models_cache = get_installed_models() if self._ollama_running else []
                self._models_cache_at = time.time()
            finally:
                self._models_refreshing = False

        threading.Thread(target=worker, daemon=True).start()

    def _settings(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH, encoding="utf-8")
        return {
            "defaultModel": get_default_model(),
            "localDefaultModel": config.get("Models", "default_model", fallback="llama3.2:3b"),
            "analysisMode": get_analysis_mode(),
            "provider": config.get("ExternalAPI", "provider", fallback="OpenAI"),
            "externalModel": config.get("ExternalAPI", "external_model", fallback="gpt-4o-mini"),
            "hasApiKey": has_api_key(),
            "ocrLanguage": get_ocr_language(),
            "tesseractPath": get_tesseract_cmd() or "",
            "cooldownSeconds": config.get("Automation", "cooldown_seconds", fallback="30"),
            "smartTrigger": config.get("Automation", "smart_trigger", fallback="true") == "true",
            "autoProtection": config.get("Automation", "auto_protection", fallback="false") == "true",
            "sensitivity": config.get("Automation", "sensitivity", fallback="70"),
            "theme": config.get("UI", "theme", fallback="system"),
            "logsDirectory": config.get("Logs", "directory", fallback=str(logs_dir())),
            "retentionDays": config.get("History", "retention_days", fallback="180"),
        }

    def _system(self):
        state = read_state()
        return {
            **state,
            "model": state.get("model") or get_default_model(),
            "auto_interval": int(state.get("auto_interval", 0) or 0),
            "protection_active": bool(state.get("protection_active", False)),
        }

    def _experimental(self):
        try:
            return experimental_summary()
        except Exception as exc:
            add_event("experimental", f"Falha ao carregar resumo experimental: {exc}", "ERROR")
            return {
                "datasets": [],
                "experiments": [],
                "latest_metrics": [],
                "totals": {"datasets": 0, "samples": 0, "experiments": 0},
            }

    def _logs(self):
        log_dir = logs_dir()
        files = []
        tail = []
        if log_dir.exists():
            for path in sorted(log_dir.glob("*.log")):
                try:
                    files.append({"name": path.name, "size": path.stat().st_size})
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-18:]
                    tail.append({"name": path.name, "lines": lines})
                except Exception:
                    pass
        return {"files": files[:12], "tail": tail[:4]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["boot", "analysis", "report", "dashboard"], required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--report")
    parser.add_argument("--duration", type=int, default=10000)
    args = parser.parse_args()

    import webview

    api = CyberDetectApi(args.report)
    if args.mode == "boot":
        url = f"{Path(args.index).resolve().as_uri()}#mode=boot&duration={args.duration}"
    else:
        url = f"{Path(args.index).resolve().as_uri()}#mode={args.mode}"

    title_map = {
        "boot": "CyberDetect",
        "analysis": "CyberDetect - Processando",
        "report": "CyberDetect - Relatorio",
        "dashboard": "CyberDetect - Central",
    }
    title = title_map[args.mode]
    width = 1360 if args.mode == "dashboard" else 720 if args.mode == "boot" else 760 if args.mode == "analysis" else 1180
    height = 860 if args.mode == "dashboard" else 720 if args.mode == "boot" else 520 if args.mode == "analysis" else 900

    webview.create_window(
        title,
        url,
        js_api=api,
        width=width,
        height=height,
        frameless=args.mode in {"boot", "analysis"},
        on_top=args.mode in {"boot", "analysis"},
        background_color="#010501",
    )
    webview.start()


if __name__ == "__main__":
    main()
