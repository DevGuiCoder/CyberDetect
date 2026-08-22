from __future__ import annotations

import re
from typing import Any


def _levenshtein(a: list[str] | str, b: list[str] | str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def _words(text: str) -> list[str]:
    return re.findall(r"\S+", str(text or "").strip().lower())


def word_error_rate(expected: str, predicted: str) -> float:
    reference = _words(expected)
    hypothesis = _words(predicted)
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return round(_levenshtein(reference, hypothesis) / len(reference), 6)


def char_error_rate(expected: str, predicted: str) -> float:
    reference = str(expected or "")
    hypothesis = str(predicted or "")
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return round(_levenshtein(reference, hypothesis) / len(reference), 6)


def evaluate_ocr_pairs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    details = []
    for index, row in enumerate(rows, 1):
        expected = str(row.get("expected_text") or row.get("expected") or row.get("texto_esperado") or "")
        predicted = str(row.get("ocr_text") or row.get("predicted_text") or row.get("texto_ocr") or row.get("predicted") or "")
        if not expected and not predicted:
            continue
        details.append({
            "id": row.get("id") or row.get("sample_id") or f"OCR-{index:06d}",
            "wer": word_error_rate(expected, predicted),
            "cer": char_error_rate(expected, predicted),
            "expected_length": len(expected),
            "predicted_length": len(predicted),
        })

    count = len(details)
    avg_wer = round(sum(item["wer"] for item in details) / count, 6) if count else None
    avg_cer = round(sum(item["cer"] for item in details) / count, 6) if count else None
    return {
        "sample_count": count,
        "average_wer": avg_wer,
        "average_cer": avg_cer,
        "details": details,
    }
