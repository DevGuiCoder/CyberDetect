import os

import customtkinter as ctk
from PIL import Image

from app.paths import asset_path
from ui.window_icon import apply_window_icon


BG = "#010501"
SURFACE = "#041404"
SURFACE_DARK = "#020902"
BORDER = "#0f5f19"
BORDER_BRIGHT = "#39ff14"
TEXT = "#c8ffc4"
MUTED = "#5fae61"
GREEN = "#39ff14"
GREEN_SOFT = "#9cff7f"
INK = "#011001"
ERROR = "#ff5c8a"
FONT = "Consolas"


def get_error_image_path():
    green_path = str(asset_path("erro_green.png"))
    if os.path.exists(green_path):
        return green_path
    return str(asset_path("erro.png"))


class ErrorFeedbackWindow(ctk.CTkToplevel):
    def __init__(
        self,
        parent=None,
        title="Erro no CyberDetect",
        message="Ocorreu um erro inesperado.",
        details="",
        suggestion="Tente novamente. Se o problema continuar, verifique as configuracoes e os logs do CyberDetect.",
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("920x640")
        self.minsize(760, 520)
        self.resizable(True, True)
        self.configure(fg_color=BG)
        apply_window_icon(self)
        self.attributes("-topmost", True)

        self.message = str(message or "Ocorreu um erro inesperado.")
        self.details = str(details or "")
        self.suggestion = str(suggestion or "")
        self.error_image = None

        self._center(920, 640)
        self._setup_ui()
        self._fade_in()
        self.lift()
        self.focus_force()
        self.after(1800, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)

    def _center(self, width, height):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self):
        shell = ctk.CTkFrame(
            self,
            fg_color=SURFACE_DARK,
            border_width=1,
            border_color=BORDER_BRIGHT,
            corner_radius=6,
        )
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        shell.grid_columnconfigure(0, weight=0, minsize=300)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        self._topline(shell)
        self._image_panel(shell)
        self._content_panel(shell)

    def _topline(self, parent):
        top = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure((0, 1, 2), weight=1)

        values = ("ERRO / CYBERDETECT", "CD-ERROR-FEEDBACK", "SYSTEM NOTICE")
        for index, value in enumerate(values):
            anchor = "w" if index == 0 else "center" if index == 1 else "e"
            ctk.CTkLabel(
                top,
                text=value,
                text_color=GREEN_SOFT,
                font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                anchor=anchor,
            ).grid(row=0, column=index, sticky="ew", padx=16, pady=12)

    def _image_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=BG, border_width=1, border_color=BORDER, corner_radius=6)
        panel.grid(row=1, column=0, sticky="nsew", padx=(18, 14), pady=18)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        image_path = get_error_image_path()
        if os.path.exists(image_path):
            image = Image.open(image_path).convert("RGBA")
            self.error_image = ctk.CTkImage(light_image=image, dark_image=image, size=(260, 260))
            ctk.CTkLabel(panel, text="", image=self.error_image).grid(row=0, column=0, padx=18, pady=18)
        else:
            ctk.CTkLabel(
                panel,
                text="!",
                font=ctk.CTkFont(family=FONT, size=104, weight="bold"),
                text_color=GREEN,
            ).grid(row=0, column=0, padx=18, pady=18)

        ctk.CTkLabel(
            panel,
            text="OCR / ANALISE / FEEDBACK",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))

    def _content_panel(self, parent):
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.grid(row=1, column=1, sticky="nsew", padx=(0, 18), pady=18)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            content,
            text="Algo deu errado",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=30, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(2, 8))

        ctk.CTkLabel(
            content,
            text=self.message,
            text_color=GREEN_SOFT,
            font=ctk.CTkFont(family=FONT, size=14),
            justify="left",
            anchor="w",
            wraplength=520,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 14))

        feedback = ctk.CTkScrollableFrame(
            content,
            fg_color=SURFACE_DARK,
            border_width=1,
            border_color=BORDER,
            corner_radius=6,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=GREEN,
        )
        feedback.grid(row=2, column=0, sticky="nsew", pady=(0, 14))
        feedback.grid_columnconfigure(0, weight=1)

        self._feedback_card(feedback, 0, "ERRO", self.message, ERROR)
        if self.details:
            self._feedback_card(feedback, 1, "DETALHES", self.details, TEXT)
        self._feedback_card(feedback, 2 if self.details else 1, "SUGESTAO", self.suggestion, GREEN_SOFT)

        actions = ctk.CTkFrame(content, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            actions,
            text="COPIAR DETALHES",
            command=self._copy_details,
            height=44,
            fg_color=SURFACE,
            hover_color="#082508",
            text_color=GREEN_SOFT,
            border_width=1,
            border_color=BORDER_BRIGHT,
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            actions,
            text="FECHAR",
            command=self.destroy,
            height=44,
            fg_color=GREEN,
            hover_color=GREEN_SOFT,
            text_color=INK,
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _feedback_card(self, parent, row, label, value, color):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=6)
        card.grid(row=row, column=0, sticky="ew", padx=10, pady=(10 if row == 0 else 0, 10))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=f"// {label}",
            text_color=GREEN,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            card,
            text=str(value),
            text_color=color,
            justify="left",
            anchor="nw",
            wraplength=500,
            font=ctk.CTkFont(family=FONT, size=13),
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))

    def _copy_details(self):
        text = f"Erro: {self.message}\nDetalhes: {self.details}\nSugestao: {self.suggestion}"
        self.clipboard_clear()
        self.clipboard_append(text)

    def _fade_in(self):
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            return

        def step(frame=0):
            if not self.winfo_exists():
                return
            progress = min(1.0, frame / 14)
            self.attributes("-alpha", progress)
            if progress < 1.0:
                self.after(16, lambda: step(frame + 1))

        step()


def show_error_feedback(parent=None, title="Erro no CyberDetect", message="", details="", suggestion=""):
    window = ErrorFeedbackWindow(parent, title=title, message=message, details=details, suggestion=suggestion)
    if parent is not None:
        try:
            window.grab_set()
        except Exception:
            pass
    return window
