from __future__ import annotations

import statistics
import time
import uuid
from datetime import datetime, timezone
from threading import Event
from typing import Any, Callable

from core.experimental.approaches import analyze_experimental_sample, normalize_approach
from core.experimental.datasets import select_samples
from core.experimental.metrics import classify_error_cases, compute_classification_metrics
from core.experimental.robustness import generate_text_variants, summarize_robustness
from core.experimental.store import (
    create_experiment,
    get_dataset,
    get_dataset_samples,
    get_experiment,
    list_experiment_results,
    save_experiment_metrics,
    save_experiment_result,
    update_experiment_status,
)
from core.ocr import get_ocr_language, get_tesseract_cmd
from core.prompt_builder import PROMPT_VERSION
from core.risk_scoring import RISK_SCORING_VERSION
from utils.logger import logger


AnalysisFn = Callable[[str, str, str], tuple[dict[str, Any], dict[str, Any]]]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _latency_stats(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"average_ms": None, "median_ms": None, "min_ms": None, "max_ms": None, "stdev_ms": None}
    return {
        "average_ms": round(sum(values) / len(values), 2),
        "median_ms": round(statistics.median(values), 2),
        "min_ms": min(values),
        "max_ms": max(values),
        "stdev_ms": round(statistics.stdev(values), 2) if len(values) > 1 else 0,
    }


def _models_for_approach(models: list[str], approach: str) -> list[str]:
    if approach == "heuristic_only":
        return ["heuristic"]
    return models


def run_batch_experiment(
    dataset_id: int,
    models: list[str],
    approaches: list[str],
    sample_limit: int = 0,
    seed: int | None = None,
    category: str = "",
    language: str = "",
    cancel_event: Event | None = None,
    analysis_fn: AnalysisFn = analyze_experimental_sample,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    cancel_event = cancel_event or Event()
    started = time.time()
    experiment_id = experiment_id or f"CD-EXP-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    approaches = [normalize_approach(item) for item in (approaches or ["hybrid"])]
    models = [str(model).strip() for model in (models or []) if str(model).strip()]
    if not models and any(item != "heuristic_only" for item in approaches):
        raise ValueError("Selecione ao menos um modelo para abordagens com IA.")

    dataset = get_dataset(dataset_id) or {}
    samples = select_samples(get_dataset_samples(dataset_id), sample_limit, seed, category, language)
    if not samples:
        raise ValueError("Dataset sem amostras para os filtros informados.")

    dataset_name = str(dataset.get("name") or samples[0].get("source_dataset") or f"dataset-{dataset_id}")
    dataset_version = str(dataset.get("version") or "1.0")
    create_experiment({
        "id": experiment_id,
        "status": "running",
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "sample_count": len(samples),
        "sample_ids": [item.get("sample_uid") or item.get("id") for item in samples],
        "seed": seed,
        "models": sorted(set(models + (["heuristic"] if "heuristic_only" in approaches else []))),
        "approaches": approaches,
        "settings": {"category": category, "language": language, "sample_limit": sample_limit},
        "prompt_version": PROMPT_VERSION,
        "risk_scoring_version": RISK_SCORING_VERSION,
        "ocr_config": {"language": get_ocr_language(), "tesseract_cmd": get_tesseract_cmd() or ""},
        "started_at": _now(),
    })

    logger.info(f"[Experimento] {experiment_id} iniciado com {len(samples)} amostras.")
    try:
        cancelled = _execute_samples(experiment_id, samples, models, approaches, cancel_event, analysis_fn)
        if cancelled:
            duration_ms = int((time.time() - started) * 1000)
            update_experiment_status(experiment_id, "cancelled", duration_ms=duration_ms)
            return {"id": experiment_id, "status": "cancelled"}

        _compute_and_store_metrics(experiment_id)
        duration_ms = int((time.time() - started) * 1000)
        update_experiment_status(experiment_id, "completed", duration_ms=duration_ms)
        logger.info(f"[Experimento] {experiment_id} finalizado em {duration_ms}ms.")
        return {"id": experiment_id, "status": "completed"}
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        update_experiment_status(experiment_id, "failed", str(exc), duration_ms)
        raise


def resume_batch_experiment(
    experiment_id: str,
    cancel_event: Event | None = None,
    analysis_fn: AnalysisFn = analyze_experimental_sample,
) -> dict[str, Any]:
    cancel_event = cancel_event or Event()
    experiment = get_experiment(experiment_id)
    if not experiment:
        raise ValueError("Experimento nao encontrado.")
    if not experiment.get("dataset_id"):
        raise ValueError("Experimento sem dataset associado.")

    started = time.time()
    samples_by_id = {
        str(item.get("sample_uid") or item.get("id")): item
        for item in get_dataset_samples(int(experiment["dataset_id"]))
    }
    samples = [samples_by_id[item] for item in experiment.get("sample_ids", []) if item in samples_by_id]
    models = [model for model in (experiment.get("models") or []) if model != "heuristic"]
    approaches = experiment.get("approaches") or ["hybrid"]
    completed = {
        (item.get("sample_uid"), item.get("model"), item.get("approach"))
        for item in list_experiment_results(experiment_id)
        if item.get("status") == "completed"
    }

    update_experiment_status(experiment_id, "running")
    cancelled = _execute_samples(experiment_id, samples, models, approaches, cancel_event, analysis_fn, skip_keys=completed)
    duration_ms = int((time.time() - started) * 1000)
    if cancelled:
        update_experiment_status(experiment_id, "cancelled", duration_ms=duration_ms)
        return {"id": experiment_id, "status": "cancelled"}

    _compute_and_store_metrics(experiment_id)
    update_experiment_status(experiment_id, "completed", duration_ms=duration_ms)
    return {"id": experiment_id, "status": "completed"}


def run_robustness_experiment(
    dataset_id: int,
    models: list[str],
    approaches: list[str],
    sample_limit: int = 0,
    seed: int | None = None,
    variant_limit: int = 10,
    cancel_event: Event | None = None,
    analysis_fn: AnalysisFn = analyze_experimental_sample,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    cancel_event = cancel_event or Event()
    started = time.time()
    experiment_id = experiment_id or f"CD-ROB-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    approaches = [normalize_approach(item) for item in (approaches or ["hybrid"])]
    models = [str(model).strip() for model in (models or []) if str(model).strip()]
    if not models and any(item != "heuristic_only" for item in approaches):
        raise ValueError("Selecione ao menos um modelo para robustez com IA.")

    dataset = get_dataset(dataset_id) or {}
    base_samples = select_samples(get_dataset_samples(dataset_id), sample_limit, seed)
    if not base_samples:
        raise ValueError("Dataset sem amostras para robustez.")

    variant_samples: list[dict[str, Any]] = []
    for sample in base_samples:
        base_uid = sample.get("sample_uid") or sample.get("id")
        for variant in generate_text_variants(str(sample.get("text") or ""), limit=variant_limit):
            variant_samples.append({
                **sample,
                "sample_uid": f"{base_uid}::{variant['name']}",
                "id": f"{base_uid}::{variant['name']}",
                "text": variant["text"],
                "metadata": {**(sample.get("metadata") or {}), "robustness_variant": variant},
            })

    dataset_name = str(dataset.get("name") or base_samples[0].get("source_dataset") or f"dataset-{dataset_id}")
    dataset_version = str(dataset.get("version") or "1.0")
    create_experiment({
        "id": experiment_id,
        "status": "running",
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "sample_count": len(variant_samples),
        "sample_ids": [item.get("sample_uid") for item in variant_samples],
        "seed": seed,
        "models": sorted(set(models + (["heuristic"] if "heuristic_only" in approaches else []))),
        "approaches": approaches,
        "settings": {"mode": "robustness", "base_sample_count": len(base_samples), "variant_limit": variant_limit},
        "prompt_version": PROMPT_VERSION,
        "risk_scoring_version": RISK_SCORING_VERSION,
        "ocr_config": {"language": get_ocr_language(), "tesseract_cmd": get_tesseract_cmd() or ""},
        "started_at": _now(),
    })

    cancelled = _execute_samples(experiment_id, variant_samples, models, approaches, cancel_event, analysis_fn)
    duration_ms = int((time.time() - started) * 1000)
    if cancelled:
        update_experiment_status(experiment_id, "cancelled", duration_ms=duration_ms)
        return {"id": experiment_id, "status": "cancelled"}

    _compute_and_store_metrics(experiment_id)
    update_experiment_status(experiment_id, "completed", duration_ms=duration_ms)
    return {"id": experiment_id, "status": "completed"}


def _execute_samples(
    experiment_id: str,
    samples: list[dict[str, Any]],
    models: list[str],
    approaches: list[str],
    cancel_event: Event,
    analysis_fn: AnalysisFn,
    skip_keys: set[tuple[Any, Any, Any]] | None = None,
) -> bool:
    skip_keys = skip_keys or set()
    for approach in approaches:
        for model in _models_for_approach(models, approach):
            for sample in samples:
                sample_uid = sample.get("sample_uid") or sample.get("id")
                if (sample_uid, model, approach) in skip_keys:
                    continue
                if cancel_event.is_set():
                    return True

                item_started = _now()
                error = ""
                status = "completed"
                try:
                    result, metadata = analysis_fn(str(sample.get("text") or ""), model, approach)
                    error = str(metadata.get("erro") or "")
                    if error:
                        status = "error"
                except Exception as exc:
                    logger.error(f"[Experimento] Falha em {experiment_id}/{model}/{sample_uid}: {exc}")
                    result = {"classificacao": "ERRO", "score_risco": 0, "fatores_risco": []}
                    metadata = {"modelo": model, "tempo_resposta_ms": 0, "erro": str(exc)}
                    error = str(exc)
                    status = "error"

                save_experiment_result(experiment_id, {
                    "sample_uid": sample_uid,
                    "model": model,
                    "approach": approach,
                    "ground_truth": sample.get("ground_truth"),
                    "prediction": result.get("classificacao", "ERRO"),
                    "score": result.get("score_risco", 0),
                    "score_modelo_original": result.get("score_modelo_original"),
                    "factors": result.get("fatores_risco") or result.get("risk_factors") or [],
                    "result": result,
                    "metadata": metadata,
                    "latency_ms": metadata.get("tempo_resposta_ms") or metadata.get("elapsed_ms") or 0,
                    "started_at": item_started,
                    "finished_at": _now(),
                    "status": status,
                    "error": error,
                })
    return False


def _compute_and_store_metrics(experiment_id: str):
    results = list_experiment_results(experiment_id)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in results:
        if item.get("prediction") == "ERRO":
            continue
        groups.setdefault((item.get("model"), item.get("approach")), []).append(item)

    for (model, approach), rows in groups.items():
        metrics = compute_classification_metrics(
            [item.get("ground_truth") for item in rows],
            [item.get("prediction") for item in rows],
        )
        errors = classify_error_cases(rows)
        metrics["latency"] = _latency_stats([int(item.get("latency_ms") or 0) for item in rows])
        metrics["errors"] = errors
        metrics["robustness"] = summarize_robustness(rows)
        metrics["ranking_fields"] = {
            "accuracy": metrics.get("accuracy"),
            "precision": metrics.get("macro", {}).get("precision"),
            "recall": metrics.get("macro", {}).get("recall"),
            "f1": metrics.get("macro", {}).get("f1"),
            "false_positive_rate": metrics.get("false_positive_rate"),
            "false_negative_rate": metrics.get("false_negative_rate"),
            "average_latency_ms": metrics.get("latency", {}).get("average_ms"),
        }
        save_experiment_metrics(experiment_id, str(model), str(approach), metrics)
