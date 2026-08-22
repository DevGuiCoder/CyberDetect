from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_APP_DESKTOP = _PROJECT_ROOT / "app" / "desktop"

if _APP_DESKTOP.exists():
    __path__.append(str(_APP_DESKTOP))
