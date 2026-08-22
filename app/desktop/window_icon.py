import os
import tkinter as tk

from app.paths import assets_dir


def _assets_dir():
    return str(assets_dir())


def get_app_icon_path():
    assets_dir = _assets_dir()
    for filename in ("app_icon.png", "icon.png", "logo.png"):
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
            return path
    return None


def get_app_ico_path():
    path = os.path.join(_assets_dir(), "app.ico")
    return path if os.path.exists(path) else None


def apply_window_icon(window):
    try:
        ico_path = get_app_ico_path()
        if ico_path:
            window.iconbitmap(ico_path)

        png_path = get_app_icon_path()
        if png_path:
            photo = tk.PhotoImage(file=png_path)
            window.iconphoto(True, photo)
            window._cyberdetect_icon_photo = photo
    except Exception:
        pass
