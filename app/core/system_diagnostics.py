from __future__ import annotations

import importlib
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from app.paths import PROJECT_ROOT, data_dir, logs_dir
from core.analyzer import get_analysis_mode, get_default_model, get_external_api_config
from core.api_key_manager import get_api_key, has_api_key
from core.history_store import DB_PATH, get_stats, init_db
from core.ocr import get_ocr_language, get_tessdata_dir, get_tesseract_cmd
from core.ollama_manager import check_ollama_running, get_installed_models, is_model_installed
from core.openai_client import test_api_key


Status = str


def _now_ms() -> int:
    return int(time.time() * 1000)


def _check(check_id: str, label: str, category: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = _now_ms()
    try:
        payload = fn()
        status = str(payload.get("status") or "OK").upper()
        if status not in {"OK", "WARN", "ERRO"}:
            status = "WARN"
        return {
            "id": check_id,
            "label": label,
            "category": category,
            "status": status,
            "detail": str(payload.get("detail") or ""),
            "metadata": payload.get("metadata") or {},
            "duration_ms": max(0, _now_ms() - started),
        }
    except Exception as exc:
        return {
            "id": check_id,
            "label": label,
            "category": category,
            "status": "ERRO",
            "detail": str(exc),
            "metadata": {},
            "duration_ms": max(0, _now_ms() - started),
        }


def _import_check(module_name: str, detail: str = "") -> dict[str, Any]:
    module = importlib.import_module(module_name)
    version = getattr(module, "__version__", "")
    text = detail or f"Modulo {module_name} importado."
    if version:
        text = f"{text} Versao: {version}."
    return {"status": "OK", "detail": text}


def _path_check(path: Path, kind: str) -> dict[str, Any]:
    exists = path.exists()
    if not exists:
        return {"status": "ERRO", "detail": f"{kind} nao encontrado: {path}"}
    writable = os.access(path, os.W_OK)
    return {
        "status": "OK" if writable else "WARN",
        "detail": f"{kind}: {path}" + ("" if writable else " (sem permissao de escrita detectada)"),
        "metadata": {"path": str(path), "writable": writable},
    }


def _summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"OK": 0, "WARN": 0, "ERRO": 0}
    for item in checks:
        counts[str(item.get("status") or "WARN").upper()] = counts.get(str(item.get("status") or "WARN").upper(), 0) + 1
    status = "ERRO" if counts["ERRO"] else "WARN" if counts["WARN"] else "OK"
    return {
        "status": status,
        "total": len(checks),
        "ok": counts["OK"],
        "warn": counts["WARN"],
        "error": counts["ERRO"],
    }


def _python_check() -> dict[str, Any]:
    version = sys.version_info
    status = "OK" if version >= (3, 11) else "WARN"
    return {
        "status": status,
        "detail": f"Python {platform.python_version()} em {sys.executable}",
        "metadata": {"executable": sys.executable, "platform": platform.platform()},
    }


def _frontend_check(base_dir: Path) -> dict[str, Any]:
    index = base_dir / "frontend" / "dist" / "index.html"
    if not index.exists():
        return {"status": "ERRO", "detail": "Build React nao encontrado em frontend/dist/index.html."}
    size = index.stat().st_size
    return {
        "status": "OK" if size > 1024 else "WARN",
        "detail": f"Build React encontrado: {index} ({size} bytes).",
        "metadata": {"path": str(index), "bytes": size},
    }


def _tesseract_check() -> dict[str, Any]:
    cmd = get_tesseract_cmd()
    if not cmd:
        return {"status": "ERRO", "detail": "Executavel do Tesseract nao encontrado."}
    try:
        completed = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        first_line = (completed.stdout or completed.stderr or "").splitlines()[0:1]
        detail = first_line[0] if first_line else "Tesseract respondeu sem versao textual."
        return {"status": "OK" if completed.returncode == 0 else "WARN", "detail": detail, "metadata": {"cmd": cmd}}
    except Exception as exc:
        return {"status": "ERRO", "detail": f"Falha ao executar Tesseract: {exc}", "metadata": {"cmd": cmd}}


def _tessdata_check(base_dir: Path) -> dict[str, Any]:
    tessdata_dir = Path(get_tessdata_dir() or base_dir / "tessdata")
    por = tessdata_dir / "por.traineddata"
    eng = tessdata_dir / "eng.traineddata"
    missing = [path.name for path in (por, eng) if not path.exists()]
    return {
        "status": "OK" if not missing else "WARN",
        "detail": f"tessdata: {tessdata_dir}; idioma OCR configurado: {get_ocr_language()}; faltando: {', '.join(missing) or 'nenhum'}.",
        "metadata": {"tessdata_dir": str(tessdata_dir), "missing": missing},
    }


def _capture_check() -> dict[str, Any]:
    from PIL import ImageGrab

    image = ImageGrab.grab(bbox=(0, 0, 1, 1), all_screens=True)
    return {
        "status": "OK" if image.size[0] >= 1 and image.size[1] >= 1 else "WARN",
        "detail": f"Captura minima executada: {image.size[0]}x{image.size[1]}.",
        "metadata": {"size": image.size},
    }


def _ollama_check(include_ollama: bool) -> dict[str, Any]:
    if not include_ollama:
        return {"status": "WARN", "detail": "Teste Ollama ignorado nesta execucao."}
    running = check_ollama_running()
    return {
        "status": "OK" if running else "WARN",
        "detail": "Ollama online." if running else "Ollama offline ou inacessivel em tempo de diagnostico.",
    }


def _model_check(include_ollama: bool) -> dict[str, Any]:
    model = get_default_model()
    mode = get_analysis_mode()
    if str(model).lower().startswith(("gpt-", "o1", "o3", "o4", "o5")):
        return {"status": "OK", "detail": f"Modelo padrao externo configurado: {model}.", "metadata": {"mode": mode}}
    if not include_ollama:
        return {"status": "WARN", "detail": f"Modelo local configurado: {model}. Instalacao nao verificada nesta execucao."}
    installed = get_installed_models() if check_ollama_running() else []
    ok = is_model_installed(model, installed)
    return {
        "status": "OK" if ok else "WARN",
        "detail": f"Modelo local padrao: {model}; instalado: {'sim' if ok else 'nao'}.",
        "metadata": {"model": model, "installed": installed},
    }


def _sqlite_check() -> dict[str, Any]:
    init_db()
    stats = get_stats()
    return {
        "status": "OK",
        "detail": f"SQLite acessivel em {DB_PATH}; {int(stats.get('total') or 0)} analises no historico.",
        "metadata": {"db_path": DB_PATH, "stats": stats},
    }


def _keyring_check() -> dict[str, Any]:
    import keyring

    backend = str(keyring.get_keyring())
    configured = has_api_key()
    return {
        "status": "OK",
        "detail": f"Keyring acessivel. API key externa configurada: {'sim' if configured else 'nao'}.",
        "metadata": {"backend": backend, "has_api_key": configured},
    }


def _external_api_check(include_external_api: bool) -> dict[str, Any]:
    external = get_external_api_config()
    provider = str(external.get("provider") or "").lower()
    model = str(external.get("external_model") or "gpt-4o-mini")
    if "openai" not in provider:
        return {"status": "WARN", "detail": "API externa nao esta configurada para OpenAI."}
    if not has_api_key():
        return {"status": "WARN", "detail": "API externa sem chave configurada no Keyring."}
    if not include_external_api:
        return {"status": "WARN", "detail": "API externa configurada; teste remoto nao executado nesta chamada."}
    api_key = get_api_key()
    ok = test_api_key(api_key or "", model)
    return {
        "status": "OK" if ok else "ERRO",
        "detail": f"Teste remoto da API externa {'passou' if ok else 'falhou'} para {model}.",
        "metadata": {"provider": external.get("provider"), "model": model},
    }


def run_system_diagnostics(
    base_dir: str | Path | None = None,
    include_capture: bool = True,
    include_external_api: bool = True,
    include_ollama: bool = True,
) -> dict[str, Any]:
    base = Path(base_dir or PROJECT_ROOT)
    runtime_data_dir = data_dir()
    runtime_logs_dir = logs_dir()

    checks = [
        _check("python", "Python", "runtime", _python_check),
        _check("frontend", "Frontend React build", "frontend", lambda: _frontend_check(base)),
        _check("pywebview", "PyWebView", "frontend", lambda: _import_check("webview", "PyWebView importado.")),
        _check("pillow", "Pillow", "ocr", lambda: _import_check("PIL", "Pillow importado.")),
        _check("opencv", "OpenCV QR", "qr", lambda: _import_check("cv2", "OpenCV importado para QR Code.")),
        _check("tesseract", "Tesseract", "ocr", _tesseract_check),
        _check("tessdata", "Tessdata PT/EN", "ocr", lambda: _tessdata_check(base)),
        _check("capture", "Captura minima", "capture", _capture_check if include_capture else lambda: {"status": "WARN", "detail": "Captura nao executada nesta chamada."}),
        _check("ollama", "Ollama", "ai", lambda: _ollama_check(include_ollama)),
        _check("default_model", "Modelo padrao", "ai", lambda: _model_check(include_ollama)),
        _check("sqlite", "SQLite historico", "storage", _sqlite_check),
        _check("data_dir", "Diretorio data", "storage", lambda: _path_check(runtime_data_dir, "Diretorio de dados")),
        _check("logs_dir", "Diretorio logs", "storage", lambda: _path_check(runtime_logs_dir, "Diretorio de logs")),
        _check("keyring", "Keyring", "security", _keyring_check),
        _check("external_api", "API externa", "ai", lambda: _external_api_check(include_external_api)),
        _check("tray", "Tray", "desktop", lambda: _import_check("pystray", "pystray importado para tray.")),
        _check("hotkey", "Hotkey keyboard", "desktop", lambda: _import_check("keyboard", "keyboard importado para hotkey global.")),
    ]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_dir": str(base),
        "summary": _summary(checks),
        "checks": checks,
        "notes": [
            "Nenhuma API key, token ou credencial e retornada no diagnostico.",
            "O teste de API externa executa chamada remota somente quando ha chave configurada e include_external_api=True.",
        ],
    }
