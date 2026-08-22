import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

COMMAND_FILE = os.path.join(tempfile.gettempdir(), "cyberdetect_dashboard_command.json")
STATE_FILE = os.path.join(tempfile.gettempdir(), "cyberdetect_dashboard_state.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, payload: Dict[str, Any]):
    temp_path = f"{path}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    last_error = None
    for _ in range(6):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    try:
        if os.path.exists(path):
            os.remove(path)
        os.replace(temp_path, path)
    except PermissionError:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise last_error


def write_command(command: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = {
        "id": str(uuid.uuid4()),
        "command": command,
        "payload": payload or {},
        "created_at": _now(),
    }
    _atomic_write(COMMAND_FILE, data)
    return data


def read_command() -> Dict[str, Any] | None:
    if not os.path.exists(COMMAND_FILE):
        return None
    try:
        with open(COMMAND_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_state(payload: Dict[str, Any]):
    data = {
        "updated_at": _now(),
        **payload,
    }
    _atomic_write(STATE_FILE, data)


def read_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
