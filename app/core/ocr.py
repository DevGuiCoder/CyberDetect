import configparser
import os
import shutil

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from app.paths import config_file, tessdata_dir
from utils.logger import logger
from utils.text_cleaner import clean_ocr_text


def get_ocr_language() -> str:
    config = configparser.ConfigParser()
    config_path = config_file()
    if os.path.exists(config_path):
        config.read(config_path)
        if "General" in config and "ocr_language" in config["General"]:
            return config["General"]["ocr_language"]
    return "por+eng"


def get_tesseract_cmd() -> str | None:
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def get_tessdata_dir() -> str | None:
    local_dir = tessdata_dir()
    if local_dir and os.path.exists(local_dir):
        return str(local_dir)
    return None


def prepare_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Melhora a legibilidade de prints pequenos antes do OCR.
    """
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    width, height = image.size
    if width < 1200 or height < 800:
        image = image.resize((width * 2, height * 2), Image.Resampling.LANCZOS)

    grayscale = ImageOps.grayscale(image)
    grayscale = ImageOps.autocontrast(grayscale)
    return grayscale.filter(ImageFilter.SHARPEN)


def extract_text(image: Image.Image) -> str:
    """
    Processa a imagem usando o Tesseract OCR e retorna o texto limpo.
    """
    try:
        lang = get_ocr_language()

        tesseract_cmd = get_tesseract_cmd()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        config_parts = ["--oem 3", "--psm 6"]
        tessdata_dir = get_tessdata_dir()
        if tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = tessdata_dir

        processed = prepare_image_for_ocr(image)
        config = " ".join(config_parts)
        try:
            raw_text = _run_tesseract(processed, lang, config)
        except pytesseract.TesseractError as first_error:
            logger.error(f"Erro do Tesseract OCR com idioma '{lang}': {first_error}")
            fallback_lang = "eng" if lang != "eng" else ""
            raw_text = _run_tesseract(processed, fallback_lang, config)
        cleaned_text = clean_ocr_text(raw_text)

        logger.info(f"OCR extraiu {len(cleaned_text)} caracteres da imagem.")
        return cleaned_text
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract OCR nao encontrado. Instale-o para continuar.")
        return ""
    except pytesseract.TesseractError as e:
        logger.error(f"Erro do Tesseract OCR: {e}")
        return ""
    except Exception as e:
        logger.error(f"Erro ao executar OCR: {e}")
        return ""


def _run_tesseract(image: Image.Image, lang: str, config: str) -> str:
    return pytesseract.image_to_string(image, lang=lang, config=config)
