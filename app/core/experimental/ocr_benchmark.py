from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path
from typing import Any, Callable

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from core.ocr import get_ocr_language, get_tessdata_dir, get_tesseract_cmd, prepare_image_for_ocr
from core.experimental.store import EXPORT_DIR
from core.experimental.text_metrics import char_error_rate, evaluate_ocr_pairs, word_error_rate
from utils.text_cleaner import clean_ocr_text


ImageExtractor = Callable[[Image.Image], str]


def parse_ocr_benchmark_content(filename: str, content: str) -> list[dict[str, Any]]:
    extension = Path(filename or "").suffix.lower()
    if extension == ".csv":
        return [dict(row) for row in csv.DictReader(io.StringIO(content or ""))]
    if extension == ".jsonl":
        rows = []
        for line in (content or "").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return [row for row in rows if isinstance(row, dict)]
    if extension == ".json":
        data = json.loads(content or "[]")
        if isinstance(data, dict):
            data = data.get("samples") or data.get("data") or data.get("items") or []
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    raise ValueError("Formato OCR nao suportado. Use CSV, JSON ou JSONL.")


def run_ocr_benchmark_from_content(filename: str, content: str) -> dict[str, Any]:
    rows = parse_ocr_benchmark_content(filename, content)
    metrics = evaluate_ocr_pairs(rows)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"ocr_benchmark_{int(time.time())}.json"
    payload = {
        "filename": filename,
        "metrics": metrics,
        "required_fields": ["expected_text", "ocr_text"],
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return {"path": str(path), **metrics}


def _tagged_image(name: str, image: Image.Image) -> Image.Image:
    tagged = image.copy()
    tagged.info["ocr_pipeline_name"] = name
    return tagged


def build_ocr_pipeline_images(image: Image.Image) -> list[dict[str, Any]]:
    source = image.convert("RGB") if image.mode not in {"RGB", "L"} else image.copy()
    width, height = source.size
    grayscale = ImageOps.grayscale(source)
    autocontrast = ImageOps.autocontrast(grayscale)
    sharpen = grayscale.filter(ImageFilter.SHARPEN)
    upscale = source.resize((max(1, width * 2), max(1, height * 2)), Image.Resampling.LANCZOS)
    pipeline = prepare_image_for_ocr(source)
    rows = [
        ("original", "Imagem original sem preprocessamento adicional.", source),
        ("grayscale", "Conversao direta para escala de cinza.", grayscale),
        ("autocontrast", "Escala de cinza com autocontraste.", autocontrast),
        ("sharpen", "Escala de cinza com filtro de nitidez.", sharpen),
        ("upscale", "Imagem ampliada 2x antes do OCR.", upscale),
        ("pipeline_completo", "Pipeline operacional do CyberDetect para OCR.", pipeline),
    ]
    return [
        {
            "name": name,
            "description": description,
            "image": _tagged_image(name, variant),
            "size": list(variant.size),
        }
        for name, description, variant in rows
    ]


def _extract_with_tesseract(image: Image.Image) -> str:
    try:
        tesseract_cmd = get_tesseract_cmd()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        tessdata_dir = get_tessdata_dir()
        if tessdata_dir:
            import os

            os.environ["TESSDATA_PREFIX"] = tessdata_dir

        lang = get_ocr_language()
        config = "--oem 3 --psm 6"
        try:
            raw_text = pytesseract.image_to_string(image, lang=lang, config=config)
        except pytesseract.TesseractError:
            fallback_lang = "eng" if lang != "eng" else ""
            raw_text = pytesseract.image_to_string(image, lang=fallback_lang, config=config)
        return clean_ocr_text(raw_text)
    except Exception:
        return ""


def _preview(text: str, limit: int = 360) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def run_ocr_pipeline_benchmark(
    image: Image.Image,
    expected_text: str = "",
    filename: str = "ocr_image",
    extractor: ImageExtractor | None = None,
    export: bool = True,
) -> dict[str, Any]:
    extractor = extractor or _extract_with_tesseract
    expected = str(expected_text or "")
    pipelines = []
    rows_for_average = []

    for item in build_ocr_pipeline_images(image):
        started = time.time()
        text = str(extractor(item["image"]) or "")
        latency_ms = int((time.time() - started) * 1000)
        row = {
            "name": item["name"],
            "description": item["description"],
            "size": item["size"],
            "latency_ms": latency_ms,
            "extracted_length": len(text),
            "ocr_text_preview": _preview(text),
            "wer": word_error_rate(expected, text) if expected else None,
            "cer": char_error_rate(expected, text) if expected else None,
        }
        pipelines.append(row)
        if expected:
            rows_for_average.append(row)

    best = None
    if expected and pipelines:
        best = min(
            pipelines,
            key=lambda row: (
                row["wer"] if row["wer"] is not None else 1,
                row["cer"] if row["cer"] is not None else 1,
            ),
        )

    average_wer = round(sum(float(row["wer"] or 0) for row in rows_for_average) / len(rows_for_average), 6) if rows_for_average else None
    average_cer = round(sum(float(row["cer"] or 0) for row in rows_for_average) / len(rows_for_average), 6) if rows_for_average else None

    payload = {
        "filename": filename,
        "expected_text_present": bool(expected),
        "sample_count": len(pipelines),
        "average_wer": average_wer,
        "average_cer": average_cer,
        "best_pipeline": best["name"] if best else None,
        "pipelines": pipelines,
    }
    if not export:
        return {"path": "", **payload}

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"ocr_pipeline_benchmark_{int(time.time())}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return {"path": str(path), **payload}
