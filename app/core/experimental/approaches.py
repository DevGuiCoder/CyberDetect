from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from core.analyzer import build_error_result, normalize_analysis_result, analyze_text
from core.ollama_manager import analyze_with_ollama
from core.openai_client import analyze_with_openai
from core.risk_scoring import apply_deterministic_risk_score


EXPERIMENTAL_APPROACHES = {
    "ai_only": "SOMENTE IA",
    "heuristic_only": "SOMENTE HEURISTICAS",
    "hybrid": "HIBRIDO",
}


def normalize_approach(value: str | None) -> str:
    clean = str(value or "hybrid").strip().lower()
    aliases = {
        "ia": "ai_only",
        "ai": "ai_only",
        "somente_ia": "ai_only",
        "heuristica": "heuristic_only",
        "heuristics": "heuristic_only",
        "somente_heuristicas": "heuristic_only",
        "hibrido": "hybrid",
        "hybrid": "hybrid",
    }
    clean = aliases.get(clean, clean)
    if clean not in EXPERIMENTAL_APPROACHES:
        raise ValueError(f"Abordagem experimental invalida: {value}")
    return clean


def _is_openai_model(model: str) -> bool:
    lower = str(model or "").lower()
    return lower.startswith(("gpt-", "o1", "o3", "o4", "o5"))


def _metadata(
    text: str,
    model: str,
    approach: str,
    time_ms: int,
    result: dict[str, Any],
    error: str | None,
    group: str,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hash_conversa": hashlib.md5(text.encode("utf-8")).hexdigest(),
        "modelo": model,
        "grupo": group,
        "experimental_approach": approach,
        "tempo_resposta_ms": time_ms,
        "score_risco": result.get("score_risco") if not error else None,
        "score_modelo_original": result.get("score_modelo_original") if not error else None,
        "classificacao": result.get("classificacao", "ERRO"),
        "tipo_golpe": result.get("tipo_golpe"),
        "num_pontos_suspeitos": len(result.get("pontos_suspeitos", [])),
        "num_tecnicas_identificadas": len(result.get("tecnicas_engenharia_social", [])),
        "num_fatores_risco": len(result.get("fatores_risco", [])),
        "json_valido": error is None,
        "tentativas_parse": 1,
        "tokens_entrada_estimado": len(text) // 4,
        "tokens_saida_estimado": len(str(result)) // 4,
        "erro": error,
    }


def analyze_experimental_sample(text: str, model: str, approach: str = "hybrid") -> tuple[dict[str, Any], dict[str, Any]]:
    approach = normalize_approach(approach)
    model = str(model or "heuristic").strip() or "heuristic"

    if approach == "hybrid":
        result, metadata = analyze_text(text, model)
        metadata = {**metadata, "experimental_approach": approach}
        return result, metadata

    if approach == "heuristic_only":
        start = time.time()
        result = apply_deterministic_risk_score({}, text)
        result.setdefault("resumo", "Classificacao gerada somente pelos fatores deterministico-heuristicos.")
        result.setdefault("recomendacao", "Verifique evidencias e canais oficiais antes de agir.")
        time_ms = int((time.time() - start) * 1000)
        return result, _metadata(text, "heuristic", approach, time_ms, result, None, "HEURISTICA")

    if _is_openai_model(model):
        raw, time_ms, error = analyze_with_openai(text, model)
        group = "API_EXTERNA"
    else:
        raw, time_ms, error = analyze_with_ollama(model, text)
        group = "LOCAL"

    if error:
        result = build_error_result(error)
    else:
        result = normalize_analysis_result(raw)
        result["score_modelo_original"] = result.get("score_risco", 0)

    return result, _metadata(text, model, approach, time_ms, result, error, group)
