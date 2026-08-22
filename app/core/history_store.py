import csv
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.paths import data_dir
from utils.logger import logger

BASE_DIR = str(data_dir().parent)
DATA_DIR = str(data_dir())
DB_PATH = os.path.join(DATA_DIR, "cyberdetect_history.sqlite3")
DB_TIMEOUT_SECONDS = 15
DB_RETRY_ATTEMPTS = 3
DB_RETRY_DELAY_SECONDS = 0.25
_INIT_LOCK = threading.RLock()

DEFAULT_APPS = [
    "WhatsApp Desktop",
    "WhatsApp Web",
    "Telegram",
    "Discord",
    "Gmail",
    "Outlook",
    "Chrome",
    "Edge",
    "Firefox",
]


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {DB_TIMEOUT_SECONDS * 1000}")
    return conn


def _is_lock_error(error: Exception) -> bool:
    return "database is locked" in str(error).lower()


def _with_retry(operation):
    last_error = None
    for attempt in range(DB_RETRY_ATTEMPTS):
        try:
            return operation()
        except sqlite3.OperationalError as error:
            last_error = error
            if not _is_lock_error(error) or attempt == DB_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(DB_RETRY_DELAY_SECONDS * (attempt + 1))
    raise last_error


def init_db():
    def operation():
        with _INIT_LOCK:
            with _connect() as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        source TEXT NOT NULL,
                        app_name TEXT,
                        model TEXT,
                        classification TEXT,
                        scam_type TEXT,
                        score INTEGER,
                        confidence TEXT,
                        elapsed_ms INTEGER,
                        input_text TEXT,
                        summary TEXT,
                        recommendation TEXT,
                        result_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                _ensure_analysis_validation_columns(conn)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS monitored_apps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        is_custom INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        level TEXT NOT NULL,
                        category TEXT NOT NULL,
                        message TEXT NOT NULL,
                        payload_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                _seed_apps(conn)

    try:
        _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao inicializar SQLite: {e}")


def _seed_apps(conn):
    now = _now()
    legacy_whatsapp = conn.execute(
        "SELECT id FROM monitored_apps WHERE name = ? AND is_custom = 0",
        ("WhatsApp",),
    ).fetchone()
    whatsapp_desktop = conn.execute(
        "SELECT id FROM monitored_apps WHERE name = ?",
        ("WhatsApp Desktop",),
    ).fetchone()
    if legacy_whatsapp and not whatsapp_desktop:
        conn.execute("UPDATE monitored_apps SET name = ? WHERE id = ?", ("WhatsApp Desktop", legacy_whatsapp["id"]))
    elif legacy_whatsapp and whatsapp_desktop:
        conn.execute("DELETE FROM monitored_apps WHERE id = ?", (legacy_whatsapp["id"],))

    for app in DEFAULT_APPS:
        conn.execute(
            """
            INSERT OR IGNORE INTO monitored_apps (name, enabled, is_custom, created_at)
            VALUES (?, 1, 0, ?)
            """,
            (app, now),
        )


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_analysis_validation_columns(conn):
    columns = _table_columns(conn, "analysis_history")
    additions = {
        "predicted_class": "TEXT",
        "ground_truth": "TEXT",
        "validated": "INTEGER NOT NULL DEFAULT 0",
        "validated_at": "TEXT",
        "validation_note": "TEXT",
        "validation_source": "TEXT",
        "validation_correct": "INTEGER",
    }
    for column, definition in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE analysis_history ADD COLUMN {column} {definition}")
    conn.execute(
        """
        UPDATE analysis_history
        SET predicted_class = classification
        WHERE predicted_class IS NULL OR predicted_class = ''
        """
    )


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value):
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except TypeError:
        return json.dumps({"repr": repr(value)}, ensure_ascii=False)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    for key in ("result_json", "metadata_json", "payload_json"):
        if key in item:
            try:
                item[key.replace("_json", "")] = json.loads(item.get(key) or "{}")
            except json.JSONDecodeError:
                item[key.replace("_json", "")] = {}
    if not item.get("predicted_class"):
        item["predicted_class"] = item.get("classification")
    return item


def _normalize_ground_truth(value: str) -> str:
    normalized = str(value or "").strip().upper()
    aliases = {
        "LEGITIMO": "SEGURO",
        "LEGITIMA": "SEGURO",
        "SAFE": "SEGURO",
        "NORMAL": "SEGURO",
        "SUSPEITA": "SUSPEITO",
        "SCAM": "GOLPE",
        "FRAUDE": "GOLPE",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"SEGURO", "SUSPEITO", "GOLPE"}:
        raise ValueError("Classificacao real invalida.")
    return normalized


def save_analysis(
    result: Dict[str, Any],
    metadata: Dict[str, Any] | None = None,
    source: str = "manual",
    input_text: str = "",
    app_name: str | None = None,
) -> bool:
    def operation():
        init_db()
        metadata = metadata_arg or {}
        try:
            score = int(result.get("score_risco", 0) or 0)
        except (TypeError, ValueError):
            score = 0

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_history (
                    created_at, source, app_name, model, classification, scam_type,
                    score, confidence, elapsed_ms, input_text, summary,
                    recommendation, result_json, metadata_json, predicted_class
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.get("timestamp") or _now(),
                    source,
                    app_name,
                    metadata.get("modelo") or metadata.get("model"),
                    result.get("classificacao", "ERRO"),
                    result.get("tipo_golpe"),
                    score,
                    result.get("confianca_analise"),
                    metadata.get("tempo_resposta_ms") or metadata.get("elapsed_ms") or 0,
                    (input_text or "")[:8000],
                    result.get("resumo", ""),
                    result.get("recomendacao", ""),
                    _safe_json(result),
                    _safe_json(metadata),
                    result.get("classificacao", "ERRO"),
                ),
            )
        return True

    metadata_arg = metadata or {}
    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao salvar analise no SQLite: {e}")
        return False


def add_event(category: str, message: str, level: str = "INFO", payload: Dict[str, Any] | None = None):
    def operation():
        init_db()
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO system_events (created_at, level, category, message, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_now(), level.upper(), category, message, _safe_json(payload or {})),
            )

    try:
        _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao registrar evento no SQLite: {e}")


def list_analyses(
    search: str = "",
    classification: str = "Todos",
    source: str = "Todas",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    def operation():
        init_db()
        query = "SELECT * FROM analysis_history WHERE 1=1"
        params: list[Any] = []

        if search.strip():
            needle = f"%{search.strip()}%"
            query += " AND (input_text LIKE ? OR summary LIKE ? OR scam_type LIKE ? OR model LIKE ? OR app_name LIKE ?)"
            params.extend([needle, needle, needle, needle, needle])

        if classification and classification != "Todos":
            query += " AND classification = ?"
            params.append(classification)

        if source and source != "Todas":
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(limit)

        with _connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao listar historico SQLite: {e}")
        return []


def get_analysis(analysis_id: int) -> Dict[str, Any] | None:
    def operation():
        init_db()
        with _connect() as conn:
            row = conn.execute("SELECT * FROM analysis_history WHERE id = ?", (analysis_id,)).fetchone()
        return _row_to_dict(row) if row else None

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao obter analise SQLite: {e}")
        return None


def validate_analysis(
    analysis_id: int,
    ground_truth: str,
    note: str = "",
    source: str = "manual",
) -> bool:
    try:
        normalized = _normalize_ground_truth(ground_truth)
    except ValueError:
        return False

    def operation():
        init_db()
        with _connect() as conn:
            row = conn.execute(
                "SELECT classification, predicted_class FROM analysis_history WHERE id = ?",
                (int(analysis_id),),
            ).fetchone()
            if not row:
                return False
            predicted = row["predicted_class"] or row["classification"] or ""
            correct = 1 if str(predicted).upper() == normalized else 0
            cursor = conn.execute(
                """
                UPDATE analysis_history
                SET ground_truth = ?,
                    validated = 1,
                    validated_at = ?,
                    validation_note = ?,
                    validation_source = ?,
                    validation_correct = ?
                WHERE id = ?
                """,
                (
                    normalized,
                    _now(),
                    str(note or "")[:800],
                    str(source or "manual")[:80],
                    correct,
                    int(analysis_id),
                ),
            )
        return cursor.rowcount > 0

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao validar analise SQLite: {e}")
        return False


def mark_analysis_feedback(
    analysis_id: int,
    is_correct: bool,
    correct_class: str = "",
    note: str = "",
    source: str = "manual_feedback",
) -> bool:
    current = get_analysis(int(analysis_id))
    if not current:
        return False

    predicted = str(current.get("predicted_class") or current.get("classification") or "").upper()
    if is_correct:
        if predicted not in {"SEGURO", "SUSPEITO", "GOLPE"}:
            return False
        ground_truth = predicted
    else:
        try:
            ground_truth = _normalize_ground_truth(correct_class)
        except ValueError:
            return False

    return validate_analysis(
        int(analysis_id),
        ground_truth,
        note=note,
        source=source,
    )


def list_validated_analyses(limit: int = 1000) -> List[Dict[str, Any]]:
    def operation():
        init_db()
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM analysis_history
                WHERE validated = 1 AND ground_truth IS NOT NULL AND ground_truth != ''
                ORDER BY datetime(validated_at) DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao listar analises validadas SQLite: {e}")
        return []


def delete_analysis(analysis_id: int) -> bool:
    def operation():
        init_db()
        with _connect() as conn:
            conn.execute("DELETE FROM analysis_history WHERE id = ?", (analysis_id,))
        return True

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao excluir analise SQLite: {e}")
        return False


def clear_history() -> bool:
    def operation():
        init_db()
        with _connect() as conn:
            conn.execute("DELETE FROM analysis_history")
        return True

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao limpar historico SQLite: {e}")
        return False


def get_stats() -> Dict[str, Any]:
    def operation():
        init_db()
        with _connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0]
            detected = conn.execute(
                "SELECT COUNT(*) FROM analysis_history WHERE classification IN ('SUSPEITO', 'GOLPE')"
            ).fetchone()[0]
            avg_score = conn.execute("SELECT AVG(score) FROM analysis_history").fetchone()[0] or 0
            top_model = conn.execute(
                """
                SELECT model, COUNT(*) as total FROM analysis_history
                WHERE model IS NOT NULL AND model != ''
                GROUP BY model ORDER BY total DESC LIMIT 1
                """
            ).fetchone()
            top_app = conn.execute(
                """
                SELECT app_name, COUNT(*) as total FROM analysis_history
                WHERE app_name IS NOT NULL AND app_name != ''
                GROUP BY app_name ORDER BY total DESC LIMIT 1
                """
            ).fetchone()
            risk_rows = conn.execute(
                """
                SELECT classification, COUNT(*) as total
                FROM analysis_history GROUP BY classification
                """
            ).fetchall()
            type_rows = conn.execute(
                """
                SELECT COALESCE(scam_type, 'Nao classificado') as scam_type, COUNT(*) as total
                FROM analysis_history GROUP BY COALESCE(scam_type, 'Nao classificado')
                ORDER BY total DESC LIMIT 8
                """
            ).fetchall()
            trend_rows = conn.execute(
                """
                SELECT substr(created_at, 1, 10) as day, COUNT(*) as total, AVG(score) as avg_score
                FROM analysis_history
                GROUP BY substr(created_at, 1, 10)
                ORDER BY day DESC LIMIT 7
                """
            ).fetchall()

        return {
            "total": total,
            "detected": detected,
            "avg_score": round(float(avg_score), 1),
            "top_model": top_model["model"] if top_model else "-",
            "top_app": top_app["app_name"] if top_app else "-",
            "risk_distribution": {row["classification"] or "ERRO": row["total"] for row in risk_rows},
            "type_distribution": [{"label": row["scam_type"], "value": row["total"]} for row in type_rows],
            "trend": [
                {
                    "day": row["day"],
                    "total": row["total"],
                    "avg_score": round(float(row["avg_score"] or 0), 1),
                }
                for row in reversed(trend_rows)
            ],
        }

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao calcular estatisticas SQLite: {e}")
        return {
            "total": 0,
            "detected": 0,
            "avg_score": 0,
            "top_model": "-",
            "top_app": "-",
            "risk_distribution": {},
            "type_distribution": [],
            "trend": [],
        }


def list_events(limit: int = 80, category: str | None = None) -> List[Dict[str, Any]]:
    def operation():
        init_db()
        query = "SELECT * FROM system_events"
        params: list[Any] = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(limit)
        with _connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao listar eventos SQLite: {e}")
        return []


def list_monitored_apps() -> List[Dict[str, Any]]:
    def operation():
        init_db()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM monitored_apps ORDER BY is_custom ASC, name COLLATE NOCASE ASC"
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao listar apps monitorados: {e}")
        return []


def set_app_enabled(app_id: int, enabled: bool) -> bool:
    def operation():
        init_db()
        with _connect() as conn:
            conn.execute("UPDATE monitored_apps SET enabled = ? WHERE id = ?", (1 if enabled else 0, app_id))
        return True

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao atualizar app monitorado: {e}")
        return False


def add_monitored_app(name: str) -> bool:
    clean = " ".join((name or "").strip().split())
    if not clean:
        return False

    def operation():
        init_db()
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO monitored_apps (name, enabled, is_custom, created_at)
                VALUES (?, 1, 1, ?)
                """,
                (clean[:80], _now()),
            )
        return True

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao adicionar app monitorado: {e}")
        return False


def remove_custom_app(app_id: int) -> bool:
    def operation():
        init_db()
        with _connect() as conn:
            conn.execute("DELETE FROM monitored_apps WHERE id = ? AND is_custom = 1", (app_id,))
        return True

    try:
        return _with_retry(operation)
    except Exception as e:
        logger.error(f"Erro ao remover app customizado: {e}")
        return False


def export_history(filepath: str, filetype: str = "json") -> bool:
    rows = list_analyses(limit=10000)
    cleaned = []
    for row in rows:
        item = dict(row)
        item.pop("result_json", None)
        item.pop("metadata_json", None)
        cleaned.append(item)

    try:
        if filetype.lower() == "csv":
            if not cleaned:
                return False
            headers = list(cleaned[0].keys())
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(cleaned)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(cleaned, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erro ao exportar historico SQLite: {e}")
        return False
