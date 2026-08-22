import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from PIL import Image

from app.paths import data_dir, logs_dir
from core.analyzer import analyze_text
from core.history_store import save_analysis
from core.ocr import extract_text
from utils.logger import logger

HISTORY_FILE = os.path.join(str(data_dir()), "benchmark_history.json")
RAW_LOG_DIR = os.path.join(str(logs_dir()), "benchmark")


def load_history() -> List[Dict[str, Any]]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar historico: {e}")
        return []


def save_history(metadata: Dict[str, Any]) -> bool:
    try:
        history = load_history()
        history.append(metadata)
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar no historico: {e}")
        return False


def _as_list(value):
    return value if isinstance(value, list) else []


def _score(result):
    try:
        return int(result.get("score_risco", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _classification(result):
    return str(result.get("classificacao", "ERRO") or "ERRO").upper()


def build_benchmark_prompt(text: str, image: Image.Image | None, ocr_text: str) -> tuple[str, str]:
    sections = []
    if text.strip():
        sections.append("TEXTO FORNECIDO PELO USUARIO:\n" + text.strip())

    visual_context = ""
    if image is not None:
        width, height = image.size
        visual_context = (
            f"Imagem/print enviado para benchmark. Dimensoes: {width}x{height}px. "
            "A avaliacao visual direta depende de modelos multimodais; para modelos locais textuais, "
            "use o OCR e os metadados da imagem como contexto."
        )
        sections.append("CONTEXTO VISUAL:\n" + visual_context)
        sections.append("OCR EXTRAIDO DA IMAGEM:\n" + (ocr_text.strip() or "OCR nao extraiu texto legivel."))

    if not sections:
        sections.append("Nenhum conteudo textual foi fornecido.")

    return "\n\n---\n\n".join(sections), visual_context


def summarize_model_result(model: str, result: Dict[str, Any], metadata: Dict[str, Any], visual_context: str, error: str = ""):
    pontos = _as_list(result.get("pontos_suspeitos"))
    tecnicas = _as_list(result.get("tecnicas_engenharia_social"))
    fatores = _as_list(result.get("fatores_risco"))
    resumo = result.get("resumo") or error or "Analise concluida sem resumo detalhado."
    recomendacao = result.get("recomendacao") or "Verifique por canais oficiais antes de agir."

    considered = []
    if visual_context:
        considered.append("metadados do print/imagem")
    considered.append("texto extraido por OCR e/ou texto colado")
    if pontos:
        considered.append(f"{len(pontos)} ponto(s) suspeito(s)")
    if tecnicas:
        considered.append("tecnicas de engenharia social detectadas")
    if fatores:
        considered.append(f"{len(fatores)} fator(es) de risco normalizado(s)")

    return {
        "id": str(uuid.uuid4()),
        "modelo": model,
        "status": "erro" if error else "concluido",
        "erro": error,
        "tempo_resposta_ms": metadata.get("tempo_resposta_ms", 0),
        "classificacao": _classification(result),
        "score_risco": _score(result),
        "score_cyberdetect": _score(result),
        "score_modelo_original": result.get("score_modelo_original"),
        "tipo_golpe": result.get("tipo_golpe"),
        "tecnicas_engenharia_social": tecnicas,
        "pontos_suspeitos": pontos,
        "fatores_risco": fatores,
        "composicao_risco": result.get("composicao_risco", {}),
        "considerou": considered,
        "explicacao": resumo,
        "recomendacao": recomendacao,
        "json_valido": bool(metadata.get("json_valido", False)),
        "_raw_response": result,
        "_metadata": metadata,
    }


def build_comparison(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [r for r in results if r.get("status") == "concluido"]
    if not completed:
        return {"resumo": "Nenhum modelo concluiu a analise.", "divergencias": ["Todos os modelos falharam."]}

    fastest = min(completed, key=lambda r: r.get("tempo_resposta_ms", 0))
    strictest = max(completed, key=lambda r: r.get("score_risco", 0))
    classifications = [r.get("classificacao", "ERRO") for r in completed]
    consensus = classifications[0] if len(set(classifications)) == 1 else "DIVERGENTE"
    avg_time = sum(r.get("tempo_resposta_ms", 0) for r in completed) / len(completed)
    avg_score = sum(r.get("score_risco", 0) for r in completed) / len(completed)
    best = max(
        completed,
        key=lambda r: (
            int(r.get("json_valido", False)),
            len(r.get("pontos_suspeitos", [])) + len(r.get("tecnicas_engenharia_social", [])),
            -r.get("tempo_resposta_ms", 0),
        ),
    )

    divergences = []
    if consensus == "DIVERGENTE":
        by_model = ", ".join(f"{r['modelo']}: {r['classificacao']}" for r in completed)
        divergences.append(f"Classificacoes divergentes: {by_model}.")
    score_values = [r.get("score_risco", 0) for r in completed]
    if max(score_values) - min(score_values) >= 25:
        divergences.append("Diferenca alta entre scores de risco.")
    if not divergences:
        divergences.append("Sem divergencias relevantes.")

    return {
        "modelo_mais_rapido": fastest["modelo"],
        "modelo_mais_rapido_tempo_ms": fastest.get("tempo_resposta_ms", 0),
        "modelo_mais_rigoroso": strictest["modelo"],
        "maior_score_risco": strictest.get("score_risco", 0),
        "consenso": consensus,
        "divergencias": divergences,
        "media_tempo_ms": int(avg_time),
        "media_score": round(avg_score, 1),
        "melhor_resposta_geral": best["modelo"],
        "resumo": (
            f"Consenso: {consensus}. Mais rapido: {fastest['modelo']}. "
            f"Mais rigoroso: {strictest['modelo']} ({strictest.get('score_risco', 0)}/100)."
        ),
    }


def _write_raw_log(benchmark_id: str, payload: Dict[str, Any]):
    try:
        os.makedirs(RAW_LOG_DIR, exist_ok=True)
        path = os.path.join(RAW_LOG_DIR, f"{benchmark_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro ao registrar log bruto do benchmark: {e}")


def run_model_laboratory(
    text: str,
    image: Image.Image | None,
    models_to_test: List[str],
    status_callback: Callable[[str, str, float], None],
    result_callback: Callable[[Dict[str, Any]], None],
    completion_callback: Callable[[List[Dict[str, Any]], Dict[str, Any]], None],
):
    def worker():
        benchmark_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        results = []
        total = max(1, len(models_to_test))

        logger.info(f"[Benchmark] Iniciando laboratorio {benchmark_id} com {len(models_to_test)} modelos.")
        ocr_start = time.time()
        ocr_text = extract_text(image) if image is not None else ""
        ocr_ms = int((time.time() - ocr_start) * 1000)
        prompt, visual_context = build_benchmark_prompt(text, image, ocr_text)
        logger.info(f"[Benchmark] OCR concluido em {ocr_ms}ms com {len(ocr_text)} caracteres.")

        for index, model in enumerate(models_to_test):
            status_callback(model, "analisando", index / total)
            logger.info(f"[Benchmark] Modelo {model} analisando ({index + 1}/{total}).")
            error = ""
            try:
                result_json, metadata = analyze_text(prompt, model)
                error = metadata.get("erro") or ""
            except Exception as e:
                logger.error(f"[Benchmark] Falha no modelo {model}: {e}")
                result_json = {
                    "classificacao": "ERRO",
                    "score_risco": 0,
                    "resumo": f"Falha ao executar modelo {model}.",
                    "recomendacao": "Verifique se o modelo esta instalado e se o Ollama esta em execucao.",
                    "pontos_suspeitos": [],
                    "tecnicas_engenharia_social": [],
                }
                metadata = {
                    "modelo": model,
                    "tempo_resposta_ms": 0,
                    "json_valido": False,
                    "erro": str(e),
                }
                error = str(e)

            item = summarize_model_result(model, result_json, metadata, visual_context, error)
            item["ocr_texto"] = ocr_text
            item["ocr_tempo_ms"] = ocr_ms
            results.append(item)
            result_callback(item)

            save_history({
                **{k: v for k, v in item.items() if not k.startswith("_")},
                "benchmark_id": benchmark_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            save_analysis(
                item.get("_raw_response", result_json),
                item.get("_metadata", metadata),
                source="benchmark",
                input_text=prompt,
            )
            status_callback(model, item["status"], (index + 1) / total)

        comparison = build_comparison(results)
        _write_raw_log(
            benchmark_id,
            {
                "benchmark_id": benchmark_id,
                "started_at": started_at,
                "ocr_text": ocr_text,
                "ocr_time_ms": ocr_ms,
                "prompt": prompt,
                "results": results,
                "comparison": comparison,
            },
        )
        completion_callback(results, comparison)

    threading.Thread(target=worker, daemon=True).start()
