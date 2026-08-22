from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "config.ini"
LEGACY_CONFIG_FILE = PROJECT_ROOT / "config.ini"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIST_INDEX = FRONTEND_DIR / "dist" / "index.html"
RESOURCES_DIR = PROJECT_ROOT / "resources"
ASSETS_DIR = RESOURCES_DIR / "assets"
LEGACY_ASSETS_DIR = PROJECT_ROOT / "assets"
TESSDATA_DIR = RESOURCES_DIR / "ocr" / "tessdata"
LEGACY_TESSDATA_DIR = PROJECT_ROOT / "tessdata"


def ensure_runtime_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def config_file() -> Path:
    if CONFIG_FILE.exists() or not LEGACY_CONFIG_FILE.exists():
        return CONFIG_FILE
    return LEGACY_CONFIG_FILE


def data_dir() -> Path:
    return DATA_DIR


def logs_dir() -> Path:
    return LOGS_DIR


def assets_dir() -> Path:
    if ASSETS_DIR.exists() or not LEGACY_ASSETS_DIR.exists():
        return ASSETS_DIR
    return LEGACY_ASSETS_DIR


def asset_path(*parts: str) -> Path:
    primary = ASSETS_DIR.joinpath(*parts)
    if primary.exists() or not LEGACY_ASSETS_DIR.exists():
        return primary
    return LEGACY_ASSETS_DIR.joinpath(*parts)


def tessdata_dir() -> Path | None:
    if TESSDATA_DIR.exists():
        return TESSDATA_DIR
    if LEGACY_TESSDATA_DIR.exists():
        return LEGACY_TESSDATA_DIR
    return None


def frontend_index() -> Path:
    return FRONTEND_DIST_INDEX
