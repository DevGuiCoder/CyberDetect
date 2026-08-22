import ctypes
import tkinter as tk
from ctypes import wintypes

from PIL import Image, ImageGrab

from utils.logger import logger


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def enable_dpi_awareness():
    """Evita divergencia entre coordenadas do Tk, Windows e ImageGrab."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    enable_dpi_awareness()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetSystemMetrics.argtypes = [wintypes.INT]
    user32.GetSystemMetrics.restype = wintypes.INT

    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return left, top, left + width, top + height


def _geometry_for_bounds(bounds: tuple[int, int, int, int]) -> str:
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    return f"{width}x{height}{left:+d}{top:+d}"


class RegionSelector(tk.Toplevel):
    """Overlay de selecao cobrindo todo o desktop virtual, incluindo multiplos monitores."""

    def __init__(self, parent):
        super().__init__(parent)
        self.bounds = get_virtual_screen_bounds()
        left, top, right, bottom = self.bounds
        self.virtual_left = left
        self.virtual_top = top
        self.virtual_width = right - left
        self.virtual_height = bottom - top

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.34)
        self.configure(background="#010501")
        self.config(cursor="crosshair")
        self.geometry(_geometry_for_bounds(self.bounds))
        self.lift()
        self.focus_force()

        self.canvas = tk.Canvas(
            self,
            cursor="crosshair",
            bg="#010501",
            bd=0,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None
        self.region = None
        self.label = self.canvas.create_text(
            24,
            20,
            anchor="nw",
            fill="#9cff7f",
            font=("Segoe UI", 13, "bold"),
            text="Arraste para selecionar qualquer regiao da tela. Esc cancela.",
        )

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda _event: self._cancel())
        self.bind("<Return>", lambda _event: self.on_release(_event) if self.rect else None)

    def _local_point(self, event):
        x = max(0, min(self.virtual_width, int(event.x)))
        y = max(0, min(self.virtual_height, int(event.y)))
        return x, y

    def _absolute_region(self, x1, y1, x2, y2):
        left = min(x1, x2) + self.virtual_left
        right = max(x1, x2) + self.virtual_left
        top = min(y1, y2) + self.virtual_top
        bottom = max(y1, y2) + self.virtual_top
        return int(left), int(top), int(right), int(bottom)

    def on_press(self, event):
        self.start_x, self.start_y = self._local_point(event)
        self.rect = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="#39ff14",
            width=3,
            fill="#0f5f19",
            stipple="gray25",
        )

    def on_drag(self, event):
        if self.rect is None:
            return
        cur_x, cur_y = self._local_point(event)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)
        width = abs(cur_x - self.start_x)
        height = abs(cur_y - self.start_y)
        self.canvas.itemconfigure(self.label, text=f"{width} x {height}px  |  solte para capturar")

    def on_release(self, event):
        if self.start_x is None or self.start_y is None:
            self._cancel()
            return

        cur_x, cur_y = self._local_point(event)
        left, top, right, bottom = self._absolute_region(self.start_x, self.start_y, cur_x, cur_y)

        if (right - left) > 10 and (bottom - top) > 10:
            self.region = (left, top, right, bottom)
        self.destroy()

    def _cancel(self):
        self.region = None
        self.destroy()


def grab_virtual_screen() -> tuple[Image.Image, tuple[int, int, int, int]]:
    bounds = get_virtual_screen_bounds()
    try:
        image = ImageGrab.grab(all_screens=True)
    except TypeError:
        image = ImageGrab.grab()
    return image, bounds


def capture_region(parent) -> Image.Image | None:
    """Seleciona uma regiao em qualquer monitor e retorna a imagem capturada."""
    try:
        selector = RegionSelector(parent)
        selector.wait_window()

        if selector.region:
            logger.info(f"Regiao capturada: {selector.region}")
            return capture_specific_region(selector.region)

        logger.info("Captura cancelada pelo usuario.")
        return None
    except Exception as e:
        logger.error(f"Erro ao capturar tela: {e}")
        return None


def select_region_coords(parent) -> tuple | None:
    try:
        selector = RegionSelector(parent)
        selector.wait_window()
        return selector.region
    except Exception as e:
        logger.error(f"Erro ao selecionar regiao: {e}")
        return None


def capture_specific_region(region: tuple) -> Image.Image | None:
    """Captura uma regiao absoluta do desktop virtual sem cortes por monitor."""
    try:
        left, top, right, bottom = [int(v) for v in region]
        if right <= left or bottom <= top:
            return None

        full_image, bounds = grab_virtual_screen()
        virtual_left, virtual_top, _virtual_right, _virtual_bottom = bounds
        crop_box = (
            left - virtual_left,
            top - virtual_top,
            right - virtual_left,
            bottom - virtual_top,
        )
        return full_image.crop(crop_box)
    except Exception as e:
        logger.error(f"Erro ao capturar regiao especifica: {e}")
        return None
