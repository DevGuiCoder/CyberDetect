from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_APP_CORE = _PROJECT_ROOT / "app" / "core"

if _APP_CORE.exists():
    __path__.append(str(_APP_CORE))
