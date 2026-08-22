from __future__ import annotations

import csv
import ctypes
import glob
import os
import subprocess
import time
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover - Windows only.
    winreg = None


INSTALL_CACHE_SECONDS = 60
PROCESS_CACHE_SECONDS = 2.0
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
BROWSER_KEYS = ("chrome", "edge", "firefox")

SUPPORTED_APPS: dict[str, dict[str, Any]] = {
    "chrome": {
        "display": "Chrome",
        "aliases": ["google chrome", "chrome"],
        "processes": ["chrome.exe"],
        "paths": [
            "{PROGRAMFILES}\\Google\\Chrome\\Application\\chrome.exe",
            "{PROGRAMFILES_X86}\\Google\\Chrome\\Application\\chrome.exe",
            "{LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe",
        ],
        "window_keywords": ["chrome"],
        "download_url": "https://www.google.com/chrome/",
    },
    "edge": {
        "display": "Edge",
        "aliases": ["microsoft edge", "edge"],
        "processes": ["msedge.exe"],
        "paths": [
            "{PROGRAMFILES}\\Microsoft\\Edge\\Application\\msedge.exe",
            "{PROGRAMFILES_X86}\\Microsoft\\Edge\\Application\\msedge.exe",
            "{LOCALAPPDATA}\\Microsoft\\Edge\\Application\\msedge.exe",
        ],
        "window_keywords": ["microsoft edge", "edge"],
        "download_url": "https://www.microsoft.com/edge",
    },
    "firefox": {
        "display": "Firefox",
        "aliases": ["mozilla firefox", "firefox"],
        "processes": ["firefox.exe"],
        "paths": [
            "{PROGRAMFILES}\\Mozilla Firefox\\firefox.exe",
            "{PROGRAMFILES_X86}\\Mozilla Firefox\\firefox.exe",
            "{LOCALAPPDATA}\\Mozilla Firefox\\firefox.exe",
        ],
        "window_keywords": ["firefox"],
        "download_url": "https://www.mozilla.org/firefox/",
    },
    "whatsapp_desktop": {
        "display": "WhatsApp Desktop",
        "aliases": ["whatsapp", "whatsapp desktop", "whatsapp app"],
        "processes": ["whatsapp.exe", "whatsapp.root.exe"],
        "paths": [
            "{LOCALAPPDATA}\\WhatsApp\\WhatsApp.exe",
            "{LOCALAPPDATA}\\Programs\\WhatsApp\\WhatsApp.exe",
            "{LOCALAPPDATA}\\Microsoft\\WindowsApps\\WhatsApp.exe",
            "{PROGRAMFILES}\\WindowsApps\\*WhatsApp*\\WhatsApp.exe",
            "{PROGRAMFILES}\\WindowsApps\\*WhatsApp*\\WhatsApp*.exe",
            "{PROGRAMFILES}\\WindowsApps\\*WhatsAppDesktop*\\WhatsApp*.exe",
        ],
        "window_keywords": ["whatsapp"],
        "download_url": "https://www.whatsapp.com/download",
    },
    "whatsapp_web": {
        "display": "WhatsApp Web",
        "aliases": ["whatsapp web", "web whatsapp", "web.whatsapp.com"],
        "processes": [],
        "paths": [],
        "window_keywords": ["whatsapp", "whatsapp web", "web.whatsapp.com"],
        "download_url": "",
        "web_only": True,
        "requires_browser": True,
    },
    "telegram": {
        "display": "Telegram",
        "aliases": ["telegram", "telegram desktop"],
        "processes": ["telegram.exe"],
        "paths": [
            "{APPDATA}\\Telegram Desktop\\Telegram.exe",
            "{LOCALAPPDATA}\\Telegram Desktop\\Telegram.exe",
            "{LOCALAPPDATA}\\Programs\\Telegram Desktop\\Telegram.exe",
        ],
        "window_keywords": ["telegram"],
        "download_url": "https://telegram.org/",
    },
    "discord": {
        "display": "Discord",
        "aliases": ["discord"],
        "processes": ["discord.exe"],
        "paths": [
            "{LOCALAPPDATA}\\Discord\\Update.exe",
            "{LOCALAPPDATA}\\Discord\\app-*\\Discord.exe",
            "{PROGRAMFILES}\\Discord\\Discord.exe",
        ],
        "window_keywords": ["discord"],
        "download_url": "https://discord.com/download",
    },
    "gmail": {
        "display": "Gmail",
        "aliases": ["gmail", "google mail"],
        "processes": [],
        "paths": [],
        "window_keywords": ["gmail", "google mail"],
        "download_url": "",
        "web_only": True,
    },
    "outlook": {
        "display": "Outlook",
        "aliases": ["microsoft outlook", "outlook", "outlook for windows", "microsoft 365"],
        "processes": ["outlook.exe", "olk.exe"],
        "paths": [
            "{PROGRAMFILES}\\Microsoft Office\\root\\Office16\\OUTLOOK.EXE",
            "{PROGRAMFILES_X86}\\Microsoft Office\\root\\Office16\\OUTLOOK.EXE",
            "{PROGRAMFILES}\\Microsoft Office\\Office16\\OUTLOOK.EXE",
            "{PROGRAMFILES_X86}\\Microsoft Office\\Office16\\OUTLOOK.EXE",
            "{LOCALAPPDATA}\\Microsoft\\WindowsApps\\olk.exe",
            "{PROGRAMFILES}\\WindowsApps\\Microsoft.OutlookForWindows_*\\olk.exe",
        ],
        "window_keywords": ["outlook"],
        "download_url": "https://www.microsoft.com/microsoft-365/outlook/",
    },
}

_INSTALL_CACHE: tuple[float, dict[str, bool]] = (0.0, {})
_PROCESS_CACHE: tuple[float, set[str]] = (0.0, set())


def normalize_app_name(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def resolve_supported_app(name: str | None) -> str | None:
    clean = normalize_app_name(name)
    if not clean:
        return None
    for key, spec in SUPPORTED_APPS.items():
        names = [spec["display"], *spec.get("aliases", [])]
        if clean in {normalize_app_name(item) for item in names}:
            return key
    for key, spec in SUPPORTED_APPS.items():
        for alias in [spec["display"], *spec.get("aliases", [])]:
            alias_clean = normalize_app_name(alias)
            if alias_clean and alias_clean in clean:
                return key
    return None


def _env_paths() -> dict[str, str]:
    return {
        "PROGRAMFILES": os.environ.get("ProgramFiles", ""),
        "PROGRAMFILES_X86": os.environ.get("ProgramFiles(x86)", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
    }


def _expand_install_pattern(pattern: str) -> str | None:
    values = _env_paths()
    for key, value in values.items():
        if f"{{{key}}}" in pattern and not value:
            return None
    try:
        return pattern.format(**values)
    except KeyError:
        return None


def _path_exists(pattern: str) -> bool:
    expanded = _expand_install_pattern(pattern)
    if not expanded:
        return False
    if any(token in expanded for token in "*?["):
        try:
            return any(Path(path).exists() for path in glob.glob(expanded))
        except OSError:
            return False
    return Path(expanded).exists()


def _registry_display_names() -> list[str]:
    if winreg is None:
        return []

    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    names: list[str] = []
    for hive, root_path in roots:
        try:
            with winreg.OpenKey(hive, root_path) as root:
                subkey_count = winreg.QueryInfoKey(root)[0]
                for index in range(subkey_count):
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, subkey_name) as subkey:
                            display, _kind = winreg.QueryValueEx(subkey, "DisplayName")
                        if display:
                            names.append(str(display))
                    except OSError:
                        continue
        except OSError:
            continue
    return names


def _installed_by_registry(key: str, display_names: list[str]) -> bool:
    spec = SUPPORTED_APPS[key]
    aliases = [normalize_app_name(item) for item in [spec["display"], *spec.get("aliases", [])]]
    for display_name in display_names:
        clean_display = normalize_app_name(display_name)
        if any(alias and alias in clean_display for alias in aliases):
            return True
    return False


def _installed_catalog() -> dict[str, bool]:
    global _INSTALL_CACHE
    cached_at, cached = _INSTALL_CACHE
    if time.time() - cached_at < INSTALL_CACHE_SECONDS and cached:
        return cached

    display_names = _registry_display_names()
    detected: dict[str, bool] = {}
    for key, spec in SUPPORTED_APPS.items():
        if spec.get("web_only"):
            continue
        detected[key] = _installed_by_registry(key, display_names) or any(
            _path_exists(pattern) for pattern in spec.get("paths", [])
        )
    browser_available = any(detected.get(key) for key in BROWSER_KEYS)
    for key, spec in SUPPORTED_APPS.items():
        if spec.get("web_only"):
            detected[key] = browser_available if spec.get("requires_browser") else True

    _INSTALL_CACHE = (time.time(), detected)
    return detected


def active_process_names() -> set[str]:
    global _PROCESS_CACHE
    cached_at, cached = _PROCESS_CACHE
    if time.time() - cached_at < PROCESS_CACHE_SECONDS and cached:
        return set(cached)

    names: set[str] = set()
    try:
        output = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        for row in csv.reader(output.splitlines()):
            if row:
                names.add(row[0].strip().lower())
    except Exception:
        pass

    if names:
        return names

    try:
        output = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process | Select-Object -ExpandProperty ProcessName",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        for line in output.splitlines():
            clean = line.strip().lower()
            if clean:
                names.add(clean if clean.endswith(".exe") else f"{clean}.exe")
    except Exception:
        pass
    _PROCESS_CACHE = (time.time(), set(names))
    return names


def app_catalog() -> dict[str, dict[str, Any]]:
    installed = _installed_catalog()
    processes = active_process_names()
    catalog: dict[str, dict[str, Any]] = {}
    for key, spec in SUPPORTED_APPS.items():
        process_list = [item.lower() for item in spec.get("processes", [])]
        active = any(process in processes for process in process_list)
        is_installed = bool(installed.get(key) or active)
        catalog[key] = {
            "key": key,
            "display": spec["display"],
            "installed": is_installed,
            "active": active,
            "web_only": bool(spec.get("web_only")),
            "download_url": spec.get("download_url") or "",
        }
    return catalog


def enrich_monitored_apps(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = app_catalog()
    enriched: list[dict[str, Any]] = []
    for app in apps:
        item = dict(app)
        key = resolve_supported_app(str(item.get("name", "")))
        enabled = bool(item.get("enabled"))

        if key and key in catalog:
            info = catalog[key]
            can_monitor = bool(info["installed"])
            if not can_monitor:
                enabled = False
                status_label = "NAO INSTALADO"
            elif info["web_only"]:
                status_label = "DISPONIVEL VIA WEB"
            elif info["active"]:
                status_label = "ATIVO"
            elif enabled:
                status_label = "MONITORANDO"
            else:
                status_label = "INSTALADO"

            item.update(
                {
                    "app_key": key,
                    "canonical_name": info["display"],
                    "enabled": enabled,
                    "installed": bool(info["installed"]),
                    "active": bool(info["active"]),
                    "web_only": bool(info["web_only"]),
                    "can_monitor": can_monitor,
                    "download_url": info["download_url"] if not can_monitor else "",
                    "status": status_label.lower().replace(" ", "_"),
                    "status_label": status_label,
                    "lock_reason": "" if can_monitor else "Aplicativo nao instalado nesta maquina.",
                    "install_hint": "Disponivel via navegador" if info["web_only"] else "Verificacao local concluida",
                }
            )
        else:
            item.update(
                {
                    "app_key": None,
                    "canonical_name": item.get("name"),
                    "installed": True,
                    "active": False,
                    "web_only": False,
                    "can_monitor": True,
                    "download_url": "",
                    "status": "monitorando" if enabled else "custom",
                    "status_label": "MONITORANDO" if enabled else "CUSTOM",
                    "lock_reason": "",
                    "install_hint": "App customizado",
                }
            )
        enriched.append(item)
    return enriched


def download_url_for_app(name: str | None) -> str:
    key = resolve_supported_app(name)
    if not key:
        return ""
    return str(SUPPORTED_APPS[key].get("download_url") or "")


def open_download_for_app(name: str | None) -> str:
    url = download_url_for_app(name)
    if url:
        webbrowser.open(url)
    return url


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def _query_process_path(pid: int) -> str:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
    return ""


def _match_by_process(process_name: str | None) -> str | None:
    clean = str(process_name or "").lower()
    if not clean:
        return None
    for key, spec in SUPPORTED_APPS.items():
        if clean in [process.lower() for process in spec.get("processes", [])]:
            return key
    return None


def _is_browser_app_key(app_key: str | None) -> bool:
    return app_key in BROWSER_KEYS


def _title_has_any(title: str | None, keywords: list[str]) -> bool:
    clean = str(title or "").lower()
    return bool(clean and any(keyword in clean for keyword in keywords))


def _match_by_title(title: str | None, process_key: str | None = None) -> str | None:
    clean = str(title or "").lower()
    if not clean:
        return None

    if process_key == "whatsapp_desktop":
        return "whatsapp_desktop"
    if _is_browser_app_key(process_key) and _title_has_any(title, ["whatsapp", "whatsapp web", "web.whatsapp.com"]):
        return "whatsapp_web"
    if "whatsapp web" in clean or "web.whatsapp.com" in clean:
        return "whatsapp_web"
    if "whatsapp" in clean:
        return "whatsapp_web" if _is_browser_app_key(process_key) or process_key is None else "whatsapp_desktop"

    for key in ["gmail", "telegram", "discord", "outlook"]:
        spec = SUPPORTED_APPS[key]
        if any(keyword in clean for keyword in spec.get("window_keywords", [])):
            return key
    return None


def get_active_window_info() -> dict[str, Any]:
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {}

        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_path = _query_process_path(int(pid.value))
        process_name = Path(process_path).name.lower() if process_path else ""

        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        process_key = _match_by_process(process_name)
        title_key = _match_by_title(title, process_key)
        app_key = title_key or process_key
        app_name = SUPPORTED_APPS[app_key]["display"] if app_key else ""

        return {
            "hwnd": int(hwnd),
            "pid": int(pid.value),
            "title": title,
            "process_name": process_name,
            "process_path": process_path,
            "app_key": app_key,
            "process_app_key": process_key,
            "app_name": app_name,
            "rect": (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)),
        }
    except Exception:
        return {}


def capture_active_window():
    info = get_active_window_info()
    rect = info.get("rect")
    if not rect:
        return None, info
    left, top, right, bottom = rect
    if right <= left or bottom <= top:
        return None, info
    try:
        from core.screenshot import capture_specific_region

        return capture_specific_region((left, top, right, bottom)), info
    except Exception:
        return None, info
