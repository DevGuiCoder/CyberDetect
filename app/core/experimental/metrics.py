from __future__ import annotations

from collections import Counter
from typing import Any

from core.experimental.datasets import MULTICLASS_LABELS, normalize_label

try:
    from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
except Exception:  # pragma: no cover - exercised only when sklearn is installed.
    accuracy_score = None
    confusion_matrix = None
    precision_recall_fscore_support = None


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 6) if den else 0.0


def _labels(labels: list[str] | tuple[str, ...] | None = None) -> list[str]:
    return list(labels or MULTICLASS_LABELS)


def _normalize_predictions(values: list[Any], labels: list[str]) -> list[str]:
    normalized = []
    for value in values:
        try:
            label = normalize_label(value)
        except ValueError:
            label = "SEGURO"
        normalized.append(label if label in labels else labels[0])
    return normalized


def _confusion_fallback(y_true: list[str], y_pred: list[str], labels: list[str]) -> list[list[int]]:
    matrix = [[0 for _ in labels] for _ in labels]
    index = {label: pos for pos, label in enumerate(labels)}
    for real, predicted in zip(y_true, y_pred):
        matrix[index[real]][index[predicted]] += 1
    return matrix


def _per_class_from_matrix(matrix: list[list[int]], labels: list[str]) -> dict[str, dict[str, float]]:
    total = sum(sum(row) for row in matrix)
    per_class: dict[str, dict[str, float]] = {}
    for i, label in enumerate(labels):
        tp = matrix[i][i]
        fp = sum(matrix[row][i] for row in range(len(labels)) if row != i)
        fn = sum(matrix[i][col] for col in range(len(labels)) if col != i)
        tn = total - tp - fp - fn
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(matrix[i]),
            "false_positive_rate": _safe_div(fp, fp + tn),
            "false_negative_rate": _safe_div(fn, fn + tp),
        }
    return per_class


def _averages(per_class: dict[str, dict[str, float]], y_true: list[str]) -> dict[str, dict[str, float]]:
    supports = Counter(y_true)
    total = max(1, len(y_true))
    macro = {
        key: round(sum(values[key] for values in per_class.values()) / max(1, len(per_class)), 6)
        for key in ("precision", "recall", "f1")
    }
    weighted = {
        key: round(sum(per_class[label][key] * supports.get(label, 0) for label in per_class) / total, 6)
        for key in ("precision", "recall", "f1")
    }
    return {"macro": macro, "weighted": weighted}


def compute_classification_metrics(
    y_true: list[Any],
    y_pred: list[Any],
    labels: list[str] | tuple[str, ...] | None = None,
    positive_label: str = "GOLPE",
) -> dict[str, Any]:
    labels = _labels(labels)
    true_values = _normalize_predictions(y_true, labels)
    pred_values = _normalize_predictions(y_pred, labels)
    if len(true_values) != len(pred_values):
        raise ValueError("y_true e y_pred precisam ter o mesmo tamanho.")

    if not true_values:
        return {
            "sample_count": 0,
            "accuracy": None,
            "macro": {},
            "weighted": {},
            "per_class": {},
            "false_positive_rate": None,
            "false_negative_rate": None,
            "confusion_matrix": {"labels": labels, "matrix": [[0 for _ in labels] for _ in labels]},
        }

    if confusion_matrix and precision_recall_fscore_support and accuracy_score:
        matrix = confusion_matrix(true_values, pred_values, labels=labels).astype(int).tolist()
        precision, recall, f1, support = precision_recall_fscore_support(
            true_values,
            pred_values,
            labels=labels,
            zero_division=0,
        )
        per_class = {
            label: {
                "precision": round(float(precision[index]), 6),
                "recall": round(float(recall[index]), 6),
                "f1": round(float(f1[index]), 6),
                "support": int(support[index]),
            }
            for index, label in enumerate(labels)
        }
        enriched = _per_class_from_matrix(matrix, labels)
        for label in labels:
            per_class[label]["false_positive_rate"] = enriched[label]["false_positive_rate"]
            per_class[label]["false_negative_rate"] = enriched[label]["false_negative_rate"]
        accuracy = round(float(accuracy_score(true_values, pred_values)), 6)
    else:
        matrix = _confusion_fallback(true_values, pred_values, labels)
        per_class = _per_class_from_matrix(matrix, labels)
        accuracy = _safe_div(sum(matrix[i][i] for i in range(len(labels))), len(true_values))

    averages = _averages(per_class, true_values)
    positive = positive_label if positive_label in per_class else labels[-1]
    return {
        "sample_count": len(true_values),
        "accuracy": accuracy,
        "macro": averages["macro"],
        "weighted": averages["weighted"],
        "per_class": per_class,
        "false_positive_rate": per_class[positive]["false_positive_rate"],
        "false_negative_rate": per_class[positive]["false_negative_rate"],
        "positive_label": positive,
        "confusion_matrix": {"labels": labels, "matrix": matrix},
    }


def classify_error_cases(results: list[dict[str, Any]], positive_label: str = "GOLPE") -> dict[str, list[dict[str, Any]]]:
    false_positives = []
    false_negatives = []
    for item in results:
        real = str(item.get("ground_truth") or "").upper()
        predicted = str(item.get("prediction") or "").upper()
        compact = {
            "sample_uid": item.get("sample_uid"),
            "model": item.get("model"),
            "approach": item.get("approach"),
            "ground_truth": real,
            "prediction": predicted,
            "score": item.get("score"),
        }
        if real != positive_label and predicted == positive_label:
            false_positives.append(compact)
        if real == positive_label and predicted != positive_label:
            false_negatives.append(compact)
    return {"false_positives": false_positives, "false_negatives": false_negatives}
