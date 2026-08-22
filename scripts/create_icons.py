import os

from PIL import Image, ImageDraw, ImageFilter

from app.paths import assets_dir


def _assets_dir():
    return str(assets_dir())


def _remove_dark_background(image):
    image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if r < 18 and g < 12 and b < 24:
                pixels[x, y] = (r, g, b, 0)
            elif r < 34 and g < 18 and b < 44:
                pixels[x, y] = (r, g, b, max(0, int(a * 0.28)))

    return image


def _contain(image, max_size):
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return image


def _build_icon(size=256, status=None):
    assets_dir = _assets_dir()
    logo_path = os.path.join(assets_dir, "logo.png")
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [size * 0.08, size * 0.08, size * 0.92, size * 0.92],
        fill=(130, 28, 214, 110),
        outline=(204, 65, 255, 160),
        width=max(2, size // 42),
    )
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(max(4, size // 22))))

    draw = ImageDraw.Draw(canvas)
    draw.ellipse(
        [size * 0.1, size * 0.1, size * 0.9, size * 0.9],
        fill=(12, 2, 20, 255),
        outline=(157, 35, 255, 230),
        width=max(2, size // 34),
    )

    if os.path.exists(logo_path):
        logo = _remove_dark_background(Image.open(logo_path))
        logo = _contain(logo, int(size * 0.68))
        x = (size - logo.width) // 2
        y = (size - logo.height) // 2
        canvas.alpha_composite(logo, (x, y))
    else:
        draw.text((size * 0.28, size * 0.38), "G", fill=(205, 86, 255, 255))

    if status:
        status_color = (37, 255, 194, 255) if status == "safe" else (255, 45, 132, 255)
        dot_size = max(15, int(size * 0.22))
        margin = max(8, int(size * 0.1))
        box = [size - dot_size - margin, size - dot_size - margin, size - margin, size - margin]
        draw.ellipse(
            [box[0] - 5, box[1] - 5, box[2] + 5, box[3] + 5],
            fill=(10, 2, 18, 255),
        )
        draw.ellipse(box, fill=status_color, outline=(255, 255, 255, 230), width=max(1, size // 96))

    return canvas


def create_placeholder_icons():
    assets_dir = _assets_dir()
    os.makedirs(assets_dir, exist_ok=True)

    app_icon = _build_icon(256)
    safe_icon = _build_icon(256, "safe")
    alert_icon = _build_icon(256, "alert")

    app_icon.save(os.path.join(assets_dir, "app_icon.png"))
    app_icon.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(assets_dir, "icon.png"))
    safe_icon.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(assets_dir, "icon_safe.png"))
    alert_icon.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(assets_dir, "icon_alert.png"))

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    app_icon.save(os.path.join(assets_dir, "app.ico"), sizes=ico_sizes)


if __name__ == "__main__":
    create_placeholder_icons()
