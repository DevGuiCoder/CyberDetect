from __future__ import annotations

from collections import defaultdict
from typing import Any


DEFAULT_THRESHOLDS = (60, 65, 70, 75, 80)
POSITIVE_LABEL = "GOLPE"


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 6) if den else 0.0


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(float(value or 0))))
    except (TypeError, ValueError):
        return 0


def _thresholds(values: list[Any] | tuple[Any, ...] | None) -> list[int]:
    if not values:
        return list(DEFAULT_THRESHOLDS)
    parsed_set = set()
    for value in values:
        try:
            parsed_set.add(max(0, min(100, int(float(value)))))
        except (TypeError, ValueError):
            continue
    parsed = sorted(parsed_set)
    return parsed or list(DEFAULT_THRESHOLDS)


def _binary_metrics(rows: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for item in rows:
        real_positive = str(item.get("ground_truth") or "").upper() == POSITIVE_LABEL
        predicted_positive = _score(item.get("score")) >= threshold
        if real_positive and predicted_positive:
            tp += 1
        elif not real_positive and predicted_positive:
            fp += 1
        elif not real_positive and not predicted_positive:
            tn += 1
        else:
            fn += 1

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return {
        "threshold": threshold,
        "sample_count": len(rows),
        "accuracy": _safe_div(tp + tn, len(rows)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": _safe_div(fp, fp + tn),
        "false_negative_rate": _safe_div(fn, fn + tp),
        "confusion_matrix": {
            "labels": ["NAO_GOLPE", "GOLPE"],
            "matrix": [[tn, fp], [fn, tp]],
        },
        "counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    }


def calibrate_thresholds(
    results: list[dict[str, Any]],
    thresholds: list[Any] | tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    valid_rows = [
        item for item in results
        if str(item.get("ground_truth") or "").upper() in {"SEGURO", "SUSPEITO", "GOLPE"}
        and str(item.get("status") or "completed") == "completed"
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in valid_rows:
        grouped[(str(item.get("model") or "-"), str(item.get("approach") or "-"))].append(item)

    rows: list[dict[str, Any]] = []
    for (model, approach), group_rows in sorted(grouped.items()):
        for threshold in _thresholds(thresholds):
            rows.append({
                "model": model,
                "approach": approach,
                **_binary_metrics(group_rows, threshold),
            })
    return rows
