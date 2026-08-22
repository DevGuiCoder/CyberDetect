import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from utils.logger import logger


def _frontend_index(base_dir):
    index_path = Path(base_dir) / "frontend" / "dist" / "index.html"
    return str(index_path) if index_path.exists() else None


def _start_webview(base_dir, mode, report_path=None, duration_ms=None):
    index_path = _frontend_index(base_dir)
    if not index_path:
        logger.info("Frontend React compilado nao encontrado.")
        return None

    command = [
        sys.executable,
        "-m",
        "ui.webview_host",
        "--mode",
        mode,
        "--index",
        index_path,
    ]
    if report_path:
        command.extend(["--report", report_path])
    if duration_ms is not None:
        command.extend(["--duration", str(int(duration_ms))])

    try:
        log_path = Path(base_dir) / "logs" / "react_windows.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=base_dir,
            stdout=log_file,
            stderr=log_file,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            exit_code = process.wait(timeout=0.6)
        except subprocess.TimeoutExpired:
            return process
        logger.error(f"Janela React ({mode}) encerrou imediatamente com codigo {exit_code}.")
        return None
    except Exception as e:
        logger.error(f"Erro ao abrir janela React ({mode}): {e}")
        return None


def show_analysis_loading(base_dir):
    return _start_webview(base_dir, "analysis")


def show_boot_loading(base_dir, duration_ms=8000):
    process = _start_webview(base_dir, "boot", duration_ms=duration_ms)
    if not process:
        return False

    def close_when_done():
        try:
            exit_code = process.wait(timeout=(duration_ms / 1000) + 4)
            if exit_code not in (0, None):
                logger.error(f"Animacao de boot encerrou com codigo {exit_code}.")
        except subprocess.TimeoutExpired:
            logger.warning("Animacao de boot nao finalizou no tempo esperado; fechando automaticamente.")
            close_react_process(process)

    threading.Thread(target=close_when_done, daemon=True).start()
    return True


def show_dashboard_window(base_dir):
    return _start_webview(base_dir, "dashboard")


def close_react_process(process):
    if not process:
        return
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception as e:
        logger.error(f"Erro ao fechar janela React: {e}")


def show_report_window(base_dir, result):
    try:
        temp_dir = Path(tempfile.gettempdir()) / "cyberdetect_reports"
        temp_dir.mkdir(parents=True, exist_ok=True)
        report_path = temp_dir / "latest_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result or {}, f, ensure_ascii=False)
        return _start_webview(base_dir, "report", str(report_path)) is not None
    except Exception as e:
        logger.error(f"Erro ao preparar relatorio React: {e}")
        return False
