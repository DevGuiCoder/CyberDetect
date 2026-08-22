from __future__ import annotations

import re
import unicodedata


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _leetspeak(text: str) -> str:
    table = str.maketrans({
        "a": "4",
        "A": "4",
        "e": "3",
        "E": "3",
        "i": "1",
        "I": "1",
        "o": "0",
        "O": "0",
        "s": "5",
        "S": "5",
    })
    return str(text or "").translate(table)


def _line_break_noise(text: str) -> str:
    words = re.findall(r"\S+", str(text or ""))
    if len(words) <= 3:
        return str(text or "")
    lines = [" ".join(words[index:index + 4]) for index in range(0, len(words), 4)]
    return "\n".join(lines)


def _spelling_noise(text: str) -> str:
    replacements = {
        "urgente": "urjente",
        "imediatamente": "imediatamete",
        "bloqueada": "bloqeda",
        "bloqueado": "bloqedo",
        "clique": "cliq",
        "senha": "senh",
        "codigo": "codgo",
        "código": "codgo",
        "verificar": "verficar",
        "pagamento": "pagameto",
    }
    result = str(text or "")
    for original, replacement in replacements.items():
        result = re.sub(original, replacement, result, flags=re.IGNORECASE)
    return result


def _small_paraphrase(text: str) -> str:
    replacements = {
        r"\burgente\b": "o quanto antes",
        r"\bimediatamente\b": "agora",
        r"\bclique\b": "acesse",
        r"\bconta\b": "cadastro",
        r"\bsenha\b": "codigo de acesso",
        r"\bpix\b": "transferencia",
        r"\bpagar\b": "regularizar",
    }
    result = str(text or "")
    for pattern, replacement in replacements.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def generate_text_variants(text: str, limit: int = 4) -> list[dict[str, str]]:
    original = str(text or "")
    variants = [
        {
            "name": "base",
            "text": original,
            "description": "Texto original sem alteracao.",
        },
        {
            "name": "sem_acentos",
            "text": _strip_accents(original),
            "description": "Acentos removidos para simular ruído de OCR/digitacao.",
        },
        {
            "name": "espacos_irregulares",
            "text": re.sub(r"\s+", "   ", original.strip()),
            "description": "Espacamento irregular sem alterar conteudo.",
        },
        {
            "name": "caixa_alternada",
            "text": "".join(ch.upper() if index % 2 else ch.lower() for index, ch in enumerate(original)),
            "description": "Caixa alternada para testar robustez lexical.",
        },
        {
            "name": "pontuacao_reduzida",
            "text": re.sub(r"[!?,.;:]+", " ", original),
            "description": "Pontuacao removida para simular texto parcial.",
        },
        {
            "name": "quebras_linha",
            "text": _line_break_noise(original),
            "description": "Quebras de linha inseridas de forma deterministica.",
        },
        {
            "name": "leetspeak",
            "text": _leetspeak(original),
            "description": "Substituicoes numericas comuns em textos ofuscados.",
        },
        {
            "name": "unicode_normalizado",
            "text": unicodedata.normalize("NFKC", original),
            "description": "Normalizacao Unicode para comparar estabilidade textual.",
        },
        {
            "name": "erros_ortograficos",
            "text": _spelling_noise(original),
            "description": "Erros ortograficos controlados em termos frequentes.",
        },
        {
            "name": "parafrase_curta",
            "text": _small_paraphrase(original),
            "description": "Pequenas substituicoes semanticas deterministicas.",
        },
    ]
    return variants[: max(1, int(limit or 1))]


def summarize_robustness(results: list[dict]) -> dict:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for item in results:
        sample_uid = str(item.get("sample_uid") or "")
        if "::" not in sample_uid:
            continue
        base_uid, variant = sample_uid.split("::", 1)
        groups.setdefault((base_uid, str(item.get("model")), str(item.get("approach"))), []).append({
            **item,
            "variant": variant,
        })

    summaries = []
    for (sample_uid, model, approach), rows in groups.items():
        base = next((row for row in rows if row["variant"] == "base"), None)
        if not base:
            continue
        comparable = [row for row in rows if row["variant"] != "base"]
        stable = [row for row in comparable if row.get("prediction") == base.get("prediction")]
        summaries.append({
            "sample_uid": sample_uid,
            "model": model,
            "approach": approach,
            "base_prediction": base.get("prediction"),
            "variant_count": len(comparable),
            "stable_count": len(stable),
            "stability_rate": round(len(stable) / len(comparable), 6) if comparable else None,
        })

    valid = [item for item in summaries if item.get("stability_rate") is not None]
    return {
        "sample_count": len(valid),
        "average_stability_rate": round(sum(item["stability_rate"] for item in valid) / len(valid), 6) if valid else None,
        "details": summaries,
    }
