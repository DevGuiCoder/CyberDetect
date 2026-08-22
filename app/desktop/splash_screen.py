import math
import os
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from utils.logger import logger


class SplashScreen:
    def __init__(self, parent, logo_path, duration_ms=15000):
        self.parent = parent
        self.logo_path = logo_path
        self.duration_ms = duration_ms
        self.window = None
        self.canvas = None
        self.photo = None
        self.base_image = None
        self.base_size = 330
        self.window_size = 460
        self.frame = 0
        self.max_frames = max(1, int(duration_ms / 16))
        self.transparent_color = "#010203"

    def show(self):
        if not os.path.exists(self.logo_path):
            logger.warning(f"Logo do splash nao encontrado: {self.logo_path}")
            return

        try:
            screen_w = self.parent.winfo_screenwidth()
            screen_h = self.parent.winfo_screenheight()
            self.base_size = max(210, min(350, int(min(screen_w, screen_h) * 0.31)))
            self.window_size = self.base_size + 118
            self.base_image = self._prepare_logo(Image.open(self.logo_path).convert("RGBA"))

            self.window = tk.Toplevel(self.parent)
            self.window.overrideredirect(True)
            self.window.configure(bg=self.transparent_color)
            self.window.attributes("-topmost", True)
            self.window.attributes("-alpha", 0.0)
            self.window.wm_attributes("-transparentcolor", self.transparent_color)

            width = self.window_size
            height = self.window_size
            x = (screen_w - width) // 2
            y = (screen_h - height) // 2
            self.window.geometry(f"{width}x{height}+{x}+{y}")

            self.canvas = tk.Canvas(
                self.window,
                width=width,
                height=height,
                bg=self.transparent_color,
                bd=0,
                highlightthickness=0,
            )
            self.canvas.pack(fill="both", expand=True)

            self._animate()
            self.window.after(self.duration_ms, self.close)
        except Exception as e:
            logger.error(f"Erro ao exibir splash screen: {e}")
            self.close()

    def _prepare_logo(self, image):
        image = image.resize((self.base_size, self.base_size), Image.Resampling.LANCZOS)
        pixels = image.load()
        width, height = image.size

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                brightness = max(r, g, b)
                purple_signal = max(0, b - r // 2, r - g)
                if brightness < 34 and purple_signal < 28:
                    pixels[x, y] = (r, g, b, 0)
                elif brightness < 72:
                    fade = max(0, min(255, int((brightness - 34) * 5.5)))
                    pixels[x, y] = (r, g, b, min(a, fade))

        return image

    def _animate(self):
        if not self.window or not self.window.winfo_exists() or self.base_image is None:
            return

        progress = min(1.0, self.frame / self.max_frames)
        entrance = min(progress / 0.18, 1.0)
        ease = 1 - pow(1 - entrance, 3)
        pulse = math.sin(progress * math.pi * 22) * 0.018
        scale = 0.86 + (0.14 * ease) + pulse
        size = max(1, int(self.base_size * scale))

        frame_image = self._render_frame(progress, size)
        self.photo = ImageTk.PhotoImage(frame_image)
        self.canvas.delete("all")
        self.canvas.create_image(self.window_size // 2, self.window_size // 2, image=self.photo)

        if progress < 0.28:
            alpha = progress / 0.28
        elif progress > 0.82:
            alpha = max(0.0, (1.0 - progress) / 0.18)
        else:
            alpha = 1.0
        self.window.attributes("-alpha", max(0.0, min(0.97, alpha)))

        self.frame += 1
        self.window.after(16, self._animate)

    def _render_frame(self, progress, logo_size):
        frame = Image.new("RGBA", (self.window_size, self.window_size), (0, 0, 0, 0))
        center = self.window_size // 2
        ring_radius = logo_size // 2 + 22
        ring_box = [
            center - ring_radius,
            center - ring_radius,
            center + ring_radius,
            center + ring_radius,
        ]

        glow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        spinner_start = -90 + (progress * 360 * 2.2)
        spinner_length = 72 + 42 * (0.5 + 0.5 * math.sin(progress * math.pi * 8))

        for width, alpha in [(22, 32), (15, 52), (9, 92)]:
            glow_draw.arc(ring_box, spinner_start, spinner_start + spinner_length, fill=(189, 20, 255, alpha), width=width)

        glow = glow.filter(ImageFilter.GaussianBlur(8))
        frame.alpha_composite(glow)

        draw = ImageDraw.Draw(frame)
        draw.arc(ring_box, 0, 360, fill=(154, 25, 214, 58), width=2)
        draw.arc(ring_box, spinner_start, spinner_start + spinner_length, fill=(229, 92, 255, 235), width=4)

        dot_angle = math.radians(spinner_start + spinner_length)
        dot_x = center + math.cos(dot_angle) * ring_radius
        dot_y = center + math.sin(dot_angle) * ring_radius
        dot_radius = 5
        draw.ellipse(
            [dot_x - dot_radius, dot_y - dot_radius, dot_x + dot_radius, dot_y + dot_radius],
            fill=(244, 127, 255, 245),
        )

        logo = self.base_image.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        logo_x = center - logo_size // 2
        logo_y = center - logo_size // 2
        frame.alpha_composite(logo, (logo_x, logo_y))

        return frame

    def close(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
