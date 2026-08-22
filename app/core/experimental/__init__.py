"""Experimental evaluation subsystem for CyberDetect.

This package is intentionally separate from the operational analysis pipeline.
It lets the laboratory run datasets, compare approaches and persist scientific
metrics without changing how the app classifies threats in day-to-day use.
"""

from core.experimental.datasets import DatasetSample, normalize_label
from core.experimental.metrics import compute_classification_metrics

__all__ = [
    "DatasetSample",
    "compute_classification_metrics",
    "normalize_label",
]
