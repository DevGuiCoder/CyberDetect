from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from core.experimental.datasets import DatasetSample
from core.history_store import DATA_DIR, _connect, _now, _safe_json, _with_retry, init_db
from utils.logger import logger


EXPORT_DIR = Path(DATA_DIR) / "experiments" / "exports"


def _json_load(value: str | None, fallback: Any):
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def init_experimental_db():
    def operation():
        init_db()
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experimental_datasets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '1.0',
                    source_path TEXT,
                    source_format TEXT,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    imported_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experimental_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    sample_uid TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ground_truth TEXT NOT NULL,
                    category TEXT,
                    language TEXT,
                    source TEXT,
                    source_dataset TEXT,
                    translated INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(dataset_id, sample_uid),
                    FOREIGN KEY(dataset_id) REFERENCES experimental_datasets(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dataset_id INTEGER,
                    dataset_name TEXT,
                    dataset_version TEXT,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    sample_ids_json TEXT NOT NULL DEFAULT '[]',
                    seed INTEGER,
                    models_json TEXT NOT NULL DEFAULT '[]',
                    approaches_json TEXT NOT NULL DEFAULT '[]',
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    prompt_version TEXT,
                    risk_scoring_version TEXT,
                    ocr_config_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT,
                    finished_at TEXT,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    sample_uid TEXT NOT NULL,
                    model TEXT NOT NULL,
                    approach TEXT NOT NULL,
                    ground_truth TEXT NOT NULL,
                    prediction TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    score_modelo_original INTEGER,
                    factors_json TEXT NOT NULL DEFAULT '[]',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    UNIQUE(experiment_id, sample_uid, model, approach)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    approach TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, model, approach)
                )
                """
            )

    try:
        _with_retry(operation)
    except Exception as exc:
        logger.error(f"Erro ao inicializar tabelas experimentais: {exc}")


def save_dataset(
    name: str,
    version: str,
    samples: list[DatasetSample],
    source_path: str = "",
    source_format: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def operation():
        init_experimental_db()
        now = _now()
        with _connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO experimental_datasets
                (name, version, source_path, source_format, sample_count, imported_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, version or "1.0", source_path, source_format, len(samples), now, _safe_json(metadata or {})),
            )
            dataset_id = int(cursor.lastrowid)
            for sample in samples:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO experimental_samples (
                        dataset_id, sample_uid, text, ground_truth, category, language, source,
                        source_dataset, translated, notes, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_id,
                        sample.id,
                        sample.text,
                        sample.ground_truth,
                        sample.category,
                        sample.language,
                        sample.source,
                        sample.source_dataset,
                        1 if sample.translated else 0,
                        sample.notes,
                        _safe_json(sample.metadata),
                    ),
                )
        return {"id": dataset_id, "name": name, "version": version or "1.0", "sample_count": len(samples)}

    return _with_retry(operation)


def list_datasets() -> list[dict[str, Any]]:
    def operation():
        init_experimental_db()
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*,
                       COUNT(s.id) as total_samples,
                       SUM(CASE WHEN s.ground_truth = 'SEGURO' THEN 1 ELSE 0 END) as seguro,
                       SUM(CASE WHEN s.ground_truth = 'SUSPEITO' THEN 1 ELSE 0 END) as suspeito,
                       SUM(CASE WHEN s.ground_truth = 'GOLPE' THEN 1 ELSE 0 END) as golpe
                FROM experimental_datasets d
                LEFT JOIN experimental_samples s ON s.dataset_id = d.id
                GROUP BY d.id
                ORDER BY datetime(d.imported_at) DESC
                """
            ).fetchall()
        return [
            {
                **dict(row),
                "metadata": _json_load(row["metadata_json"], {}),
                "label_distribution": {
                    "SEGURO": int(row["seguro"] or 0),
                    "SUSPEITO": int(row["suspeito"] or 0),
                    "GOLPE": int(row["golpe"] or 0),
                },
            }
            for row in rows
        ]

    return _with_retry(operation)


def get_dataset(dataset_id: int) -> dict[str, Any] | None:
    def operation():
        init_experimental_db()
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM experimental_datasets WHERE id = ?",
                (int(dataset_id),),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = _json_load(item.get("metadata_json"), {})
        return item

    return _with_retry(operation)


def get_dataset_samples(dataset_id: int) -> list[dict[str, Any]]:
    def operation():
        init_experimental_db()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM experimental_samples WHERE dataset_id = ? ORDER BY id ASC",
                (int(dataset_id),),
            ).fetchall()
        return [
            {
                **dict(row),
                "id": row["sample_uid"],
                "metadata": _json_load(row["metadata_json"], {}),
                "translated": bool(row["translated"]),
            }
            for row in rows
        ]

    return _with_retry(operation)


def create_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    def operation():
        init_experimental_db()
        now = _now()
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO experiments (
                    id, created_at, updated_at, status, dataset_id, dataset_name, dataset_version,
                    sample_count, sample_ids_json, seed, models_json, approaches_json, settings_json,
                    prompt_version, risk_scoring_version, ocr_config_json, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    now,
                    now,
                    payload.get("status", "running"),
                    payload.get("dataset_id"),
                    payload.get("dataset_name"),
                    payload.get("dataset_version"),
                    int(payload.get("sample_count") or 0),
                    _safe_json(payload.get("sample_ids") or []),
                    payload.get("seed"),
                    _safe_json(payload.get("models") or []),
                    _safe_json(payload.get("approaches") or []),
                    _safe_json(payload.get("settings") or {}),
                    payload.get("prompt_version"),
                    payload.get("risk_scoring_version"),
                    _safe_json(payload.get("ocr_config") or {}),
                    payload.get("started_at") or now,
                ),
            )
        return get_experiment(payload["id"]) or payload

    return _with_retry(operation)


def update_experiment_status(experiment_id: str, status: str, error: str = "", duration_ms: int = 0):
    def operation():
        init_experimental_db()
        now = _now()
        finished_at = now if status in {"completed", "cancelled", "failed"} else None
        with _connect() as conn:
            conn.execute(
                """
                UPDATE experiments
                SET status = ?, updated_at = ?, finished_at = COALESCE(?, finished_at),
                    duration_ms = CASE WHEN ? > 0 THEN ? ELSE duration_ms END,
                    error = COALESCE(NULLIF(?, ''), error)
                WHERE id = ?
                """,
                (status, now, finished_at, duration_ms, duration_ms, error, experiment_id),
            )

    _with_retry(operation)


def save_experiment_result(experiment_id: str, item: dict[str, Any]):
    def operation():
        init_experimental_db()
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_results (
                    experiment_id, sample_uid, model, approach, ground_truth, prediction, score,
                    score_modelo_original, factors_json, result_json, metadata_json, latency_ms,
                    started_at, finished_at, status, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    item.get("sample_uid"),
                    item.get("model"),
                    item.get("approach"),
                    item.get("ground_truth"),
                    item.get("prediction"),
                    int(item.get("score") or 0),
                    item.get("score_modelo_original"),
                    _safe_json(item.get("factors") or []),
                    _safe_json(item.get("result") or {}),
                    _safe_json(item.get("metadata") or {}),
                    int(item.get("latency_ms") or 0),
                    item.get("started_at") or _now(),
                    item.get("finished_at") or _now(),
                    item.get("status") or "completed",
                    item.get("error") or "",
                ),
            )

    _with_retry(operation)


def list_experiment_results(experiment_id: str, model: str = "", approach: str = "") -> list[dict[str, Any]]:
    def operation():
        init_experimental_db()
        query = "SELECT * FROM experiment_results WHERE experiment_id = ?"
        params: list[Any] = [experiment_id]
        if model:
            query += " AND model = ?"
            params.append(model)
        if approach:
            query += " AND approach = ?"
            params.append(approach)
        query += " ORDER BY id ASC"
        with _connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                **dict(row),
                "factors": _json_load(row["factors_json"], []),
                "result": _json_load(row["result_json"], {}),
                "metadata": _json_load(row["metadata_json"], {}),
            }
            for row in rows
        ]

    return _with_retry(operation)


def save_experiment_metrics(experiment_id: str, model: str, approach: str, metrics: dict[str, Any]):
    def operation():
        init_experimental_db()
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_metrics
                (experiment_id, model, approach, metrics_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (experiment_id, model, approach, _safe_json(metrics), _now()),
            )

    _with_retry(operation)


def list_experiment_metrics(experiment_id: str) -> list[dict[str, Any]]:
    def operation():
        init_experimental_db()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment_metrics WHERE experiment_id = ? ORDER BY model, approach",
                (experiment_id,),
            ).fetchall()
        return [{**dict(row), "metrics": _json_load(row["metrics_json"], {})} for row in rows]

    return _with_retry(operation)


def list_experiments(limit: int = 30) -> list[dict[str, Any]]:
    def operation():
        init_experimental_db()
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*,
                       COUNT(r.id) as completed_results,
                       SUM(CASE WHEN r.status = 'error' THEN 1 ELSE 0 END) as error_results
                FROM experiments e
                LEFT JOIN experiment_results r ON r.experiment_id = e.id
                GROUP BY e.id
                ORDER BY datetime(e.created_at) DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_experiment_row(row) for row in rows]

    return _with_retry(operation)


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    def operation():
        init_experimental_db()
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT e.*,
                       COUNT(r.id) as completed_results,
                       SUM(CASE WHEN r.status = 'error' THEN 1 ELSE 0 END) as error_results
                FROM experiments e
                LEFT JOIN experiment_results r ON r.experiment_id = e.id
                WHERE e.id = ?
                GROUP BY e.id
                """,
                (experiment_id,),
            ).fetchone()
        return _experiment_row(row) if row else None

    return _with_retry(operation)


def _experiment_row(row) -> dict[str, Any]:
    item = dict(row)
    item["sample_ids"] = _json_load(item.pop("sample_ids_json", "[]"), [])
    item["models"] = _json_load(item.pop("models_json", "[]"), [])
    item["approaches"] = _json_load(item.pop("approaches_json", "[]"), [])
    item["settings"] = _json_load(item.pop("settings_json", "{}"), {})
    item["ocr_config"] = _json_load(item.pop("ocr_config_json", "{}"), {})
    item["completed_results"] = int(item.get("completed_results") or 0)
    item["error_results"] = int(item.get("error_results") or 0)
    expected = _expected_result_count(int(item.get("sample_count") or 0), item.get("models") or [], item.get("approaches") or [])
    item["expected_results"] = expected
    item["progress_percent"] = round(min(100, item["completed_results"] * 100 / expected), 1)
    return item


def _expected_result_count(sample_count: int, models: list[str], approaches: list[str]) -> int:
    non_heuristic_models = [model for model in models if str(model) != "heuristic"]
    total_per_sample = 0
    for approach in approaches:
        total_per_sample += 1 if approach == "heuristic_only" else max(1, len(non_heuristic_models))
    return max(1, sample_count * max(1, total_per_sample))


def experimental_summary() -> dict[str, Any]:
    datasets = list_datasets()
    experiments = list_experiments(limit=10)
    latest = experiments[0] if experiments else None
    latest_metrics = list_experiment_metrics(latest["id"]) if latest else []
    return {
        "datasets": datasets,
        "experiments": experiments,
        "latest_metrics": latest_metrics,
        "rankings": _rankings_from_metrics(latest_metrics),
        "totals": {
            "datasets": len(datasets),
            "samples": sum(int(item.get("total_samples") or 0) for item in datasets),
            "experiments": len(experiments),
        },
    }


def _rankings_from_metrics(metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    for row in metrics_rows:
        metrics = row.get("metrics") or {}
        macro = metrics.get("macro") or {}
        latency = metrics.get("latency") or {}
        candidates.append({
            "model": row.get("model"),
            "approach": row.get("approach"),
            "accuracy": metrics.get("accuracy"),
            "precision": macro.get("precision"),
            "recall": macro.get("recall"),
            "f1": macro.get("f1"),
            "false_negative_rate": metrics.get("false_negative_rate"),
            "average_latency_ms": latency.get("average_ms"),
        })

    def best_max(key: str):
        valid = [item for item in candidates if item.get(key) is not None]
        return max(valid, key=lambda item: item[key]) if valid else None

    def best_min(key: str):
        valid = [item for item in candidates if item.get(key) is not None]
        return min(valid, key=lambda item: item[key]) if valid else None

    return {
        "best_accuracy": best_max("accuracy"),
        "best_precision": best_max("precision"),
        "best_recall": best_max("recall"),
        "best_f1": best_max("f1"),
        "lowest_false_negative_rate": best_min("false_negative_rate"),
        "fastest": best_min("average_latency_ms"),
    }


def export_experiment(experiment_id: str, filetype: str = "json") -> str:
    experiment = get_experiment(experiment_id)
    if not experiment:
        raise ValueError("Experimento nao encontrado.")
    results = list_experiment_results(experiment_id)
    metrics = list_experiment_metrics(experiment_id)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ext = "csv" if str(filetype).lower() == "csv" else "json"
    path = EXPORT_DIR / f"{experiment_id}.{ext}"

    if ext == "csv":
        rows = []
        for item in results:
            rows.append({
                "experiment_id": experiment_id,
                "sample_uid": item.get("sample_uid"),
                "model": item.get("model"),
                "approach": item.get("approach"),
                "ground_truth": item.get("ground_truth"),
                "prediction": item.get("prediction"),
                "score": item.get("score"),
                "score_modelo_original": item.get("score_modelo_original"),
                "latency_ms": item.get("latency_ms"),
                "status": item.get("status"),
                "error": item.get("error"),
            })
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()) if rows else ["experiment_id"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                {"experiment": experiment, "results": results, "metrics": metrics},
                file,
                ensure_ascii=False,
                indent=2,
            )
    return str(path)


def generate_experiment_report(experiment_id: str) -> str:
    experiment = get_experiment(experiment_id)
    if not experiment:
        raise ValueError("Experimento nao encontrado.")
    metrics = list_experiment_metrics(experiment_id)
    results = list_experiment_results(experiment_id)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"{experiment_id}_relatorio.md"

    lines = [
        f"# Relatorio Experimental CyberDetect",
        "",
        f"Experimento: `{experiment_id}`",
        f"Status: `{experiment.get('status')}`",
        f"Dataset: `{experiment.get('dataset_name') or '-'}`",
        f"Amostras: `{experiment.get('sample_count')}`",
        f"Modelos: `{', '.join(experiment.get('models') or []) or '-'}`",
        f"Abordagens: `{', '.join(experiment.get('approaches') or []) or '-'}`",
        f"Seed: `{experiment.get('seed') if experiment.get('seed') is not None else 'N/A'}`",
        f"Prompt version: `{experiment.get('prompt_version') or 'N/A'}`",
        f"Risk scoring version: `{experiment.get('risk_scoring_version') or 'N/A'}`",
        "",
        "## Resultados",
        "",
    ]

    if not metrics:
        lines.append("RESULTADOS AINDA NAO COLETADOS.")
    else:
        lines.extend([
            "| Modelo | Abordagem | Accuracy | Precision | Recall | F1 | FPR | FNR | Latencia media ms |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for row in metrics:
            item = row.get("metrics") or {}
            macro = item.get("macro") or {}
            latency = item.get("latency") or {}
            lines.append(
                "| {model} | {approach} | {acc} | {precision} | {recall} | {f1} | {fpr} | {fnr} | {lat} |".format(
                    model=row.get("model"),
                    approach=row.get("approach"),
                    acc=_fmt_metric(item.get("accuracy")),
                    precision=_fmt_metric(macro.get("precision")),
                    recall=_fmt_metric(macro.get("recall")),
                    f1=_fmt_metric(macro.get("f1")),
                    fpr=_fmt_metric(item.get("false_positive_rate")),
                    fnr=_fmt_metric(item.get("false_negative_rate")),
                    lat=latency.get("average_ms") if latency.get("average_ms") is not None else "N/A",
                )
            )

    lines.extend(["", "## Matrizes de Confusao", ""])
    for row in metrics:
        item = row.get("metrics") or {}
        matrix = item.get("confusion_matrix") or {}
        labels = matrix.get("labels") or []
        values = matrix.get("matrix") or []
        lines.append(f"### {row.get('model')} / {row.get('approach')}")
        if labels and values:
            lines.append("")
            lines.append("| Real \\ Predito | " + " | ".join(labels) + " |")
            lines.append("| --- | " + " | ".join("---:" for _ in labels) + " |")
            for label, row_values in zip(labels, values):
                lines.append("| " + label + " | " + " | ".join(str(value) for value in row_values) + " |")
        else:
            lines.append("N/A")
        lines.append("")

    false_positives = [item for item in results if item.get("ground_truth") != "GOLPE" and item.get("prediction") == "GOLPE"]
    false_negatives = [item for item in results if item.get("ground_truth") == "GOLPE" and item.get("prediction") != "GOLPE"]
    lines.extend([
        "## Erros Criticos",
        "",
        f"Falsos positivos: `{len(false_positives)}`",
        f"Falsos negativos: `{len(false_negatives)}`",
        "",
        "## Observacao",
        "",
        "Este relatorio apresenta dados coletados pelo sistema. Ele nao interpreta cientificamente os resultados nem inventa conclusoes.",
        "",
    ])

    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return str(path)


def _fmt_metric(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "N/A"
