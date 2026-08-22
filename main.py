import hashlib
import os
import sys
import threading
import time
import traceback
import ctypes
import tempfile
from tkinter import messagebox
from ctypes import wintypes

import customtkinter as ctk
import keyboard

from app.paths import PROJECT_ROOT, asset_path, ensure_runtime_dirs, logs_dir
from core.analyzer import analyze_text, get_default_model
from core.dashboard_bridge import read_command, write_state
from core.history_store import add_event, init_db, save_analysis
from core.ocr import extract_text
from core.qr_analyzer import analyze_qr_codes, apply_qr_analysis_to_result, build_qr_analysis_text
from core.screenshot import capture_region, capture_specific_region, select_region_coords
from ui.error_feedback_window import show_error_feedback
from ui.privacy_warning import PrivacyWarningWindow
from ui.react_windows import (
    close_react_process,
    show_analysis_loading,
    show_boot_loading,
    show_dashboard_window,
    show_report_window,
)

from ui.report_window import ReportWindow
from ui.splash_screen import SplashScreen
from ui.tray import TrayApp
from utils.logger import logger

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

ERROR_ALREADY_EXISTS = 183
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SINGLE_INSTANCE_MUTEX = "Local\\CyberDetect_SingleInstance"
INSTANCE_PID_FILE = os.path.join(tempfile.gettempdir(), "cyberdetect_single_instance.pid")


def _is_process_alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = wintypes.DWORD()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return bool(ok and exit_code.value == STILL_ACTIVE)
    except Exception:
        return False


def _read_running_pid() -> int | None:
    try:
        if not os.path.exists(INSTANCE_PID_FILE):
            return None
        with open(INSTANCE_PID_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _write_running_pid():
    try:
        with open(INSTANCE_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.error(f"Nao foi possivel gravar PID da instancia: {e}")


def _clear_running_pid():
    try:
        if _read_running_pid() == os.getpid() and os.path.exists(INSTANCE_PID_FILE):
            os.remove(INSTANCE_PID_FILE)
    except Exception:
        pass


def install_crash_logging():
    ensure_runtime_dirs()
    log_dir = str(logs_dir())
    os.makedirs(log_dir, exist_ok=True)
    crash_log = os.path.join(log_dir, "fatal.log")

    def write_exception(prefix, exc_type, exc_value, exc_traceback):
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error(f"{prefix}: {exc_value}")
        print(f"[CyberDetect] {prefix}: {exc_value}", file=sys.stderr)
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {prefix}\n")
            f.write(message)

    def handle_exception(exc_type, exc_value, exc_traceback):
        write_exception("Excecao fatal", exc_type, exc_value, exc_traceback)

    def handle_thread_exception(args):
        write_exception("Excecao fatal em thread", args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception


def get_icon_path(state="safe"):
    if state == "alert":
        return str(asset_path("icon_alert.png"))
    return str(asset_path("icon_safe.png"))


def get_logo_path():
    return str(asset_path("logo.png"))


def acquire_single_instance_lock():
    mutex_handle = None
    file_handle = None
    try:
        running_pid = _read_running_pid()
        if running_pid and _is_process_alive(running_pid):
            logger.warning(f"Instancia existente detectada via PID {running_pid}.")
            return None, False

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        mutex_handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
        if not mutex_handle:
            return None, False
        already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS

        try:
            import msvcrt

            lock_path = os.path.join(tempfile.gettempdir(), "cyberdetect_single_instance.lock")
            file_handle = open(lock_path, "a+b")
            file_handle.seek(0)
            if not file_handle.read(1):
                file_handle.seek(0)
                file_handle.write(b"1")
                file_handle.flush()
            file_handle.seek(0)
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            already_running = True
        except Exception as e:
            logger.error(f"Nao foi possivel criar trava de arquivo: {e}")

        if already_running:
            return (mutex_handle, file_handle), False

        _write_running_pid()
        logger.info(f"Trava de instancia adquirida pelo PID {os.getpid()}.")
        return (mutex_handle, file_handle), True
    except Exception as e:
        logger.error(f"Nao foi possivel criar trava de instancia unica: {e}")
        return None, True


def release_single_instance_lock(handle):
    _clear_running_pid()
    if not handle:
        return
    if isinstance(handle, tuple):
        mutex_handle, file_handle = handle
        if file_handle:
            try:
                import msvcrt

                file_handle.seek(0)
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            try:
                file_handle.close()
            except Exception:
                pass
        handle = mutex_handle

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(handle)
    except Exception:
        pass


def show_already_running_error():
    logger.warning("Tentativa de iniciar uma segunda instancia do CyberDetect.")
    print("[CyberDetect] O CyberDetect ja esta em execucao.", file=sys.stderr)
    native_alert_shown = False
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "O CyberDetect já está em execução.\n\nVerifique o ícone na bandeja/tray do Windows.",
            "CyberDetect já está em execução",
            0x00000010 | 0x00040000 | 0x00010000,
        )
        native_alert_shown = True
    except Exception:
        pass

    if native_alert_shown:
        return

    root = ctk.CTk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror(
        "CyberDetect já está em execução",
        "O CyberDetect já está em execução.\n\nVerifique o ícone na bandeja/tray do Windows.",
        parent=root,
    )
    window = show_error_feedback(
        root,
        title="CyberDetect já está em execução",
        message="O CyberDetect já está aberto e rodando em segundo plano.",
        details="Foi detectada outra instância ativa do aplicativo. Verifique o ícone na bandeja/tray do Windows.",
        suggestion="Use o menu da bandeja para analisar a tela, abrir configurações ou encerrar o CyberDetect antes de iniciar novamente.",
    )
    root.wait_window(window)
    root.destroy()


def build_error_report(message: str, recommendation: str) -> dict:
    return {
        "classificacao": "ERRO",
        "score_risco": 0,
        "tipo_golpe": None,
        "resumo": message,
        "recomendacao": recommendation,
        "pontos_suspeitos": [],
        "tecnicas_engenharia_social": [],
    }


def should_alert_user(result: dict) -> bool:
    try:
        score = int(result.get("score_risco", 0) or 0)
    except (TypeError, ValueError):
        score = 0

    if result.get("classificacao") in {"SUSPEITO", "GOLPE"} or score >= 31:
        return True

    pontos = result.get("pontos_suspeitos", [])
    if isinstance(pontos, list):
        for ponto in pontos:
            if not isinstance(ponto, dict):
                continue
            gravidade = str(ponto.get("gravidade", "")).strip().upper()
            if gravidade in {"MEDIA", "ALTA"}:
                return True

    return False


class CyberDetectApp:
    def __init__(self):
        self.auto_interval = 0
        self.auto_region = None
        self.last_text_hash = None
        self.auto_monitor_thread = None
        self.analysis_lock = threading.Lock()
        self.base_dir = str(PROJECT_ROOT)
        self.dashboard_process = None
        self.capture_active = False
        self.capture_command_id = None
        self.last_capture_finished_id = None
        current_command = read_command()
        self.last_dashboard_command_id = current_command.get("id") if current_command else None
        init_db()

        self.tray = TrayApp(
            run_analysis_callback=self.run_analysis_flow,
            get_icon_path_callback=get_icon_path,
            auto_interval_callback=self.set_auto_interval,
            get_auto_interval_callback=self.get_auto_interval,
            open_dashboard_callback=self.open_dashboard,
            shutdown_callback=self.shutdown,
        )
        self.privacy_accepted = False

    def setup_hotkeys(self):
        try:
            keyboard.add_hotkey("ctrl+shift+g", self.run_analysis_flow)
            logger.info("Atalho global configurado: Ctrl+Shift+G")
        except Exception as e:
            logger.error(f"Nao foi possivel configurar o atalho global: {e}")

    def run_analysis_flow(self, capture_command_id=None):
        if not self.analysis_lock.acquire(blocking=False):
            logger.info("Analise ja em andamento; ignorando nova solicitacao.")
            if capture_command_id:
                self._mark_capture_finished(capture_command_id)
            return
        threading.Thread(target=self._analysis_worker, args=(capture_command_id,), daemon=True).start()

    def _release_analysis_lock(self):
        try:
            self.analysis_lock.release()
        except RuntimeError:
            pass

    def _analysis_worker(self, capture_command_id=None):
        try:
            model = get_default_model()

            if model.lower().startswith(("gpt-", "o1", "o3", "o4", "o5")) and not self.privacy_accepted:
                def on_accept():
                    self.privacy_accepted = True
                    threading.Thread(
                        target=self._analysis_worker_continue,
                        args=(model, capture_command_id),
                        daemon=True,
                    ).start()

                def on_cancel():
                    if capture_command_id:
                        self._mark_capture_finished(capture_command_id)
                    self._release_analysis_lock()

                self.tray.hidden_root.after(
                    0,
                    lambda: self._show_privacy_warning(on_accept, on_cancel),
                )
                return

            self._analysis_worker_continue(model, capture_command_id)
        except Exception as e:
            logger.error(f"Erro inesperado no fluxo de analise: {e}")
            if capture_command_id:
                self._mark_capture_finished(capture_command_id)
            self._release_analysis_lock()

    def _show_privacy_warning(self, callback, on_cancel=None):
        pw = PrivacyWarningWindow(self.tray.hidden_root, callback, on_cancel)
        pw.focus()

    def _analysis_worker_continue(self, model, capture_command_id=None):
        loading_process = None
        try:
            logger.info("Iniciando fluxo de captura...")

            img_container = []
            event = threading.Event()

            def do_capture():
                try:
                    img_container.append(capture_region(self.tray.hidden_root))
                except Exception as e:
                    logger.error(f"Erro inesperado durante captura: {e}")
                    img_container.append(None)
                finally:
                    event.set()

            if capture_command_id:
                self._mark_capture_started(capture_command_id)
            self.tray.hidden_root.after(0, do_capture)
            event.wait()
            if capture_command_id:
                self._mark_capture_finished(capture_command_id)

            img = img_container[0] if img_container else None
            if not img:
                return

            loading_process = show_analysis_loading(self.base_dir)
            text = extract_text(img)
            qr_analysis = analyze_qr_codes(img)
            analysis_text = build_qr_analysis_text(text, qr_analysis)
            if not analysis_text:
                logger.warning("Nenhum texto encontrado na imagem.")
                close_react_process(loading_process)
                loading_process = None
                self._show_report_async(build_error_report(
                    "Nenhum texto legivel ou QR Code foi encontrado na imagem.",
                    "Selecione uma area maior do print, com a conversa ou QR Code bem visivel, e tente novamente.",
                ))
                return

            result, _metadata = analyze_text(analysis_text, model)
            result = apply_qr_analysis_to_result(result, qr_analysis, analysis_text)
            _metadata = {
                **_metadata,
                "qr_detected": len(qr_analysis.get("items") or []),
                "qr_detector_available": bool(qr_analysis.get("available")),
                "qr_detector_error": qr_analysis.get("error") or "",
            }
            save_analysis(result, _metadata, source="capture", input_text=analysis_text)
            add_event("analysis", f"Analise por captura concluida: {result.get('classificacao')}", "INFO", _metadata)
            classif = result.get("classificacao", "ERRO")
            self.tray.update_icon("alert" if classif in ["SUSPEITO", "GOLPE"] else "safe")
            close_react_process(loading_process)
            loading_process = None
            self._show_report_async(result)
        except Exception as e:
            logger.error(f"Erro inesperado na analise: {e}")
            if capture_command_id:
                self._mark_capture_finished(capture_command_id)
            close_react_process(loading_process)
            loading_process = None
            self._show_report_async(build_error_report(
                f"Erro inesperado na analise: {e}",
                "Tente novamente. Se persistir, verifique logs e configuracoes do motor de analise.",
            ))
        finally:
            close_react_process(loading_process)
            self._release_analysis_lock()

    def _show_report_async(self, result, force_front=False):
        try:
            self.tray.hidden_root.after(0, lambda: self._show_report(result, force_front))
        except Exception as e:
            logger.error(f"Nao foi possivel agendar relatorio: {e}")

    def _show_report(self, result, force_front=False):
        try:
            if result.get("classificacao") == "ERRO":
                show_error_feedback(
                    self.tray.hidden_root,
                    title="Erro na análise",
                    message=result.get("resumo", "Não foi possível concluir a análise."),
                    details=result.get("recomendacao", ""),
                    suggestion="Revise a mensagem acima, ajuste as configurações se necessário e tente executar a análise novamente.",
                )
                return

            if show_report_window(self.base_dir, result):
                return
            rw = ReportWindow(self.tray.hidden_root, result)
            if force_front:
                rw.attributes("-topmost", True)
                rw.lift()
                rw.focus_force()
                rw.after(1500, lambda: rw.attributes("-topmost", False) if rw.winfo_exists() else None)
            rw.focus()
        except Exception as e:
            logger.error(f"Erro ao abrir janela de relatorio: {e}")

    def get_auto_interval(self):
        return self.auto_interval

    def set_auto_interval(self, interval):
        if interval == self.auto_interval:
            return

        old_interval = self.auto_interval
        self.auto_interval = interval

        if interval > 0:
            logger.info(f"Monitoramento ativado para cada {self._format_interval(interval)}.")
            if old_interval == 0:
                self.tray.hidden_root.after(0, self._start_auto_monitor)
        else:
            logger.info("Monitoramento automatico desativado.")
            self.auto_region = None

    def _format_interval(self, interval_seconds):
        if interval_seconds % 60 == 0:
            minutes = interval_seconds // 60
            unit = "minuto" if minutes == 1 else "minutos"
            return f"{minutes} {unit}"
        unit = "segundo" if interval_seconds == 1 else "segundos"
        return f"{interval_seconds} {unit}"

    def _start_auto_monitor(self):
        logger.info("Selecione a regiao para monitoramento continuo.")
        self.auto_region = select_region_coords(self.tray.hidden_root)

        if not self.auto_region:
            logger.info("Selecao de regiao cancelada. Desativando monitoramento automatico.")
            self.auto_interval = 0
            if self.tray.icon:
                self.tray.icon.menu = self.tray.build_menu()
            return

        self.last_text_hash = None

        if not self.auto_monitor_thread or not self.auto_monitor_thread.is_alive():
            self.auto_monitor_thread = threading.Thread(target=self._auto_monitor_loop, daemon=True)
            self.auto_monitor_thread.start()

    def _auto_monitor_loop(self):
        first_cycle = True
        while self.auto_interval > 0 and self.auto_region:
            current_interval = self.auto_interval
            if first_cycle:
                first_cycle = False
            else:
                target_time = time.time() + current_interval
                while time.time() < target_time:
                    if self.auto_interval == 0 or self.auto_interval != current_interval:
                        break
                    time.sleep(1)

                if self.auto_interval == 0:
                    break

                if self.auto_interval != current_interval:
                    continue

            logger.info("Auto-Monitor: Capturando regiao...")
            self._run_auto_monitor_cycle()

    def _run_auto_monitor_cycle(self):
        if not self.analysis_lock.acquire(blocking=False):
            logger.info("Auto-Monitor: Analise manual/automatica ja em andamento; pulando ciclo.")
            return

        try:
            img = capture_specific_region(self.auto_region)
            if not img:
                return

            text = extract_text(img)
            qr_analysis = analyze_qr_codes(img)
            analysis_text = build_qr_analysis_text(text, qr_analysis)
            if not analysis_text or not analysis_text.strip():
                logger.info("Auto-Monitor: Nenhum texto legivel ou QR Code detectado na regiao.")
                return

            current_hash = hashlib.md5(analysis_text.encode("utf-8")).hexdigest()
            if current_hash == self.last_text_hash:
                logger.info("Auto-Monitor: Texto nao mudou desde a ultima analise.")
                return

            logger.info("Auto-Monitor: Novo texto/QR detectado, enviando para analise.")
            self.last_text_hash = current_hash
            model = get_default_model()
            result, _metadata = analyze_text(analysis_text, model)
            result = apply_qr_analysis_to_result(result, qr_analysis, analysis_text)
            _metadata = {
                **_metadata,
                "qr_detected": len(qr_analysis.get("items") or []),
                "qr_detector_available": bool(qr_analysis.get("available")),
                "qr_detector_error": qr_analysis.get("error") or "",
            }
            save_analysis(result, _metadata, source="auto", input_text=analysis_text)
            add_event("protection", f"Monitoramento automatico analisou novo texto: {result.get('classificacao')}", "INFO", _metadata)

            if should_alert_user(result):
                self.tray.update_icon("alert")
                self._show_report_async(result, force_front=True)
            else:
                self.tray.update_icon("safe")
        except Exception as e:
            logger.error(f"Erro no monitoramento automatico: {e}")
        finally:
            self._release_analysis_lock()

    def open_dashboard(self):
        try:
            if self.dashboard_process and self.dashboard_process.poll() is None:
                return
            self.dashboard_process = show_dashboard_window(self.base_dir)
        except Exception as e:
            logger.error(f"Erro ao abrir painel principal: {e}")

    def shutdown(self):
        self.auto_interval = 0
        if self.dashboard_process:
            close_react_process(self.dashboard_process)
            self.dashboard_process = None
        try:
            keyboard.unhook_all_hotkeys()
        except Exception as e:
            logger.error(f"Nao foi possivel remover hotkeys globais: {e}")

    def _poll_dashboard_commands(self):
        try:
            command = read_command()
            if command and command.get("id") != self.last_dashboard_command_id:
                self.last_dashboard_command_id = command.get("id")
                name = command.get("command")
                payload = command.get("payload") or {}
                if name == "set_auto_interval":
                    self.set_auto_interval(int(payload.get("interval", 0) or 0))
                elif name == "run_screen_analysis":
                    self.run_analysis_flow(capture_command_id=command.get("id"))
        except Exception as e:
            logger.error(f"Erro ao processar comando do dashboard: {e}")
        finally:
            self.tray.hidden_root.after(700, self._poll_dashboard_commands)

    def _dashboard_state_payload(self):
        return {
            "auto_interval": self.auto_interval,
            "protection_active": self.auto_interval > 0,
            "model": get_default_model(),
            "auto_region_selected": self.auto_region is not None,
            "capture_active": self.capture_active,
            "capture_command_id": self.capture_command_id,
            "last_capture_finished_id": self.last_capture_finished_id,
        }

    def _write_dashboard_state(self):
        write_state(self._dashboard_state_payload())

    def _mark_capture_started(self, command_id):
        self.capture_active = True
        self.capture_command_id = command_id
        self._write_dashboard_state()

    def _mark_capture_finished(self, command_id):
        self.capture_active = False
        self.capture_command_id = None
        self.last_capture_finished_id = command_id
        self._write_dashboard_state()

    def _publish_dashboard_state(self):
        try:
            self._write_dashboard_state()
        except Exception as e:
            logger.error(f"Erro ao publicar estado do dashboard: {e}")
        finally:
            self.tray.hidden_root.after(1000, self._publish_dashboard_state)

    def start(self):
        logger.info("Iniciando CyberDetect...")

        icon_path = get_icon_path()
        app_icon_path = str(asset_path("app_icon.png"))
        app_ico_path = str(asset_path("app.ico"))
        if not os.path.exists(icon_path) or not os.path.exists(app_icon_path) or not os.path.exists(app_ico_path):
            try:
                from scripts import create_icons

                create_icons.create_placeholder_icons()
            except Exception:
                pass

        if not show_boot_loading(self.base_dir, duration_ms=8000):
            SplashScreen(self.tray.hidden_root, get_logo_path(), duration_ms=8000).show()

        self.setup_hotkeys()
        self.tray.hidden_root.after(200, self._poll_dashboard_commands)
        self.tray.hidden_root.after(200, self._publish_dashboard_state)
        self.open_dashboard()
        self.tray.run()


if __name__ == "__main__":
    install_crash_logging()
    lock_handle, lock_acquired = acquire_single_instance_lock()
    if not lock_acquired:
        show_already_running_error()
        release_single_instance_lock(lock_handle)
        sys.exit(0)

    try:
        app = CyberDetectApp()
        app.start()
    except Exception:
        logger.exception("Falha fatal ao iniciar CyberDetect.")
        try:
            root = ctk.CTk()
            root.withdraw()
            window = show_error_feedback(
                root,
                title="Erro fatal ao iniciar",
                message="O CyberDetect não conseguiu iniciar.",
                details=traceback.format_exc(limit=4),
                suggestion="Feche o aplicativo, verifique se as dependências estão instaladas e tente novamente.",
            )
            root.wait_window(window)
            root.destroy()
        except Exception:
            pass
        raise
    finally:
        release_single_instance_lock(lock_handle)
