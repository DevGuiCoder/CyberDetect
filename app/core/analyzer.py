import configparser
import hashlib
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from app.paths import config_file
from core.api_key_manager import has_api_key
from core.ollama_manager import analyze_with_ollama
from core.openai_client import analyze_with_openai
from core.risk_scoring import apply_deterministic_risk_score
from core.url_analyzer import analyze_urls_in_text
from utils.logger import logger

VALID_CLASSIFICATIONS = {"SEGURO", "SUSPEITO", "GOLPE"}
VALID_CONFIDENCE = {"BAIXA", "MEDIA", "ALTA"}
VALID_ACTIONS = {
    "IGNORAR",
    "BLOQUEAR",
    "VERIFICAR_CANAL_OFICIAL",
    "NAO_CLICAR",
    "NAO_PAGAR",
    "NAO_ENVIAR_DADOS",
    "DENUNCIAR",
    "CONTATAR_BANCO",
    "OUTRA",
}
RISK_PATTERNS = [
    (r"\bpix\b|transferencia|deposito|pagamento", 18, "pedido ou mencao de pagamento/transferencia"),
    (r"\bbanco\b|conta bloqueada|cartao|central de seguranca", 18, "uso de contexto bancario"),
    (r"senha|token|codigo|cpf|dados|confirme|confirmar|valide|validar", 25, "pedido de dados ou credenciais"),
    (r"urgente|imediatamente|agora|10 minutos|bloqueio|sera debitado|cancelar", 18, "pressao de urgencia ou ameaca"),
    (r"https?://|www\.|\.com|\.br|bit\.ly|wa\.me|t\.me", 22, "link externo na conversa"),
    (r"premio|sorteio|liberacao|taxa|fgts|emprego|vaga", 14, "oferta ou beneficio que pode exigir acao"),
    (r"filho|mae|pai|troquei de numero|celular quebrou", 18, "possivel impostor familiar"),
]


def _as_short_text(value: Any, fallback: str = "") -> str:
    if value is None or isinstance(value, (dict, list)):
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _as_string_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = _as_short_text(item)
        if text:
            items.append(text[:220])
    return items[:limit]


def _normalize_pontos(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    pontos = []
    for item in value:
        if not isinstance(item, dict):
            continue
        gravidade = _as_short_text(item.get("gravidade"), "BAIXA").upper()
        if gravidade not in {"BAIXA", "MEDIA", "ALTA"}:
            gravidade = "BAIXA"
        pontos.append({
            "trecho": _as_short_text(item.get("trecho"), "Trecho nao especificado")[:240],
            "motivo": _as_short_text(item.get("motivo"), "Sinal de risco identificado.")[:360],
            "gravidade": gravidade,
        })
    return pontos[:8]


def _normalize_links(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    links = []
    for item in value:
        if isinstance(item, dict):
            conteudo = _as_short_text(item.get("conteudo"))
            motivo = _as_short_text(item.get("motivo"), "Pode representar risco ao usuario.")
        else:
            conteudo = _as_short_text(item)
            motivo = "Conteudo potencialmente suspeito."
        if conteudo:
            links.append({"conteudo": conteudo[:240], "motivo": motivo[:360]})
    return links[:8]


def _matching_excerpt(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 35)
    end = min(len(text), match.end() + 35)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    return excerpt or "Trecho identificado pelo OCR"


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_accents.lower()


def _load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config_path = config_file()
    if os.path.exists(config_path):
        config.read(config_path, encoding="utf-8")
    return config


def get_local_default_model() -> str:
    config = _load_config()
    if "Models" in config and "default_model" in config["Models"]:
        return config["Models"]["default_model"].strip() or "llama3.2:3b"
    return "llama3.2:3b"


def get_external_api_config() -> dict:
    config = _load_config()
    return {
        "provider": config.get("ExternalAPI", "provider", fallback="OpenAI").strip(),
        "external_model": config.get("ExternalAPI", "external_model", fallback="gpt-4o-mini").strip(),
    }


def get_analysis_mode() -> str:
    config = _load_config()
    mode = config.get("Analysis", "default_mode", fallback="automatico").strip().lower()
    return mode if mode in {"local", "api_externa", "automatico"} else "automatico"


def is_external_api_ready() -> bool:
    external = get_external_api_config()
    provider = external["provider"].lower()
    return bool(has_api_key() and external["external_model"] and "openai" in provider)


def get_default_model() -> str:
    mode = get_analysis_mode()
    external = get_external_api_config()

    if mode == "api_externa":
        return external["external_model"] or "gpt-4o-mini"

    if mode == "automatico" and is_external_api_ready():
        return external["external_model"] or "gpt-4o-mini"

    return get_local_default_model()


def build_error_result(message: str) -> Dict[str, Any]:
    return {
        "score_risco": 0,
        "classificacao": "ERRO",
        "tipo_golpe": None,
        "resumo": message,
        "pontos_suspeitos": [],
        "tecnicas_engenharia_social": [],
        "confianca_analise": "BAIXA",
        "tipos_possiveis": [],
        "dados_sensiveis_solicitados": [],
        "links_ou_arquivos_suspeitos": [],
        "indicadores_de_legitimidade": [],
        "acao_recomendada": "VERIFICAR_CANAL_OFICIAL",
        "recomendacao": "Revise as configuracoes do motor de analise e tente novamente.",
    }


def normalize_analysis_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Garante uma estrutura estavel para a UI e corrige pequenas variacoes dos modelos.
    """
    if not isinstance(result, dict):
        return build_error_result("O motor de analise retornou uma resposta invalida.")

    normalized = dict(result)

    try:
        score = int(float(normalized.get("score_risco", 0)))
    except (TypeError, ValueError):
        score = 0
    normalized.setdefault("score_modelo_original", max(0, min(100, score)))
    normalized["score_risco"] = max(0, min(100, score))

    classif = str(normalized.get("classificacao", "")).strip().upper()
    aliases = {
        "NORMAL": "SEGURO",
        "SAFE": "SEGURO",
        "SUSPEITA": "SUSPEITO",
        "ALERTA": "SUSPEITO",
        "FRAUDE": "GOLPE",
        "SCAM": "GOLPE",
    }
    classif = aliases.get(classif, classif)
    if classif not in VALID_CLASSIFICATIONS:
        score = normalized["score_risco"]
        if score <= 30:
            classif = "SEGURO"
        elif score <= 69:
            classif = "SUSPEITO"
        else:
            classif = "GOLPE"
    normalized["classificacao"] = classif

    score = normalized["score_risco"]
    if classif == "SEGURO" and score > 30:
        normalized["score_risco"] = 30
    elif classif == "SUSPEITO" and not 31 <= score <= 69:
        normalized["score_risco"] = 50
    elif classif == "GOLPE" and score < 70:
        normalized["score_risco"] = 70

    normalized["pontos_suspeitos"] = _normalize_pontos(normalized.get("pontos_suspeitos"))
    normalized["tecnicas_engenharia_social"] = _as_string_list(
        normalized.get("tecnicas_engenharia_social")
    )

    tipo_golpe = normalized.get("tipo_golpe")
    normalized["tipo_golpe"] = _as_short_text(tipo_golpe) if tipo_golpe else None

    confianca = _as_short_text(normalized.get("confianca_analise"), "MEDIA").upper()
    normalized["confianca_analise"] = confianca if confianca in VALID_CONFIDENCE else "MEDIA"

    acao = _as_short_text(normalized.get("acao_recomendada"), "VERIFICAR_CANAL_OFICIAL").upper()
    normalized["acao_recomendada"] = acao if acao in VALID_ACTIONS else "VERIFICAR_CANAL_OFICIAL"

    normalized["resumo"] = _as_short_text(normalized.get("resumo"), "Analise concluida.")[:500]
    normalized["recomendacao"] = _as_short_text(
        normalized.get("recomendacao"),
        "Evite compartilhar dados pessoais e confirme por canais oficiais.",
    )[:700]
    for key in [
        "tipos_possiveis",
        "dados_sensiveis_solicitados",
        "indicadores_de_legitimidade",
        "fatores_risco_identificados",
        "risk_factors_detected",
    ]:
        normalized[key] = _as_string_list(normalized.get(key))
    normalized["links_ou_arquivos_suspeitos"] = _normalize_links(
        normalized.get("links_ou_arquivos_suspeitos")
    )
    return normalized


def apply_local_risk_heuristics(text: str, result: Dict[str, Any]) -> Dict[str, Any]:
    lowered = _fold_text(text)
    hits = []
    url_analysis = analyze_urls_in_text(text)

    for pattern, _weight, reason in RISK_PATTERNS:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            hits.append((reason, _matching_excerpt(text, match)))

    if not hits and not url_analysis:
        return result

    adjusted = dict(result)
    if url_analysis:
        adjusted["url_analysis"] = url_analysis[:8]
        adjusted["analise_url"] = url_analysis[:8]

    pontos = list(adjusted.get("pontos_suspeitos", []))
    existing_reasons = {p.get("motivo") for p in pontos if isinstance(p, dict)}
    for reason, excerpt in hits:
        motivo = f"Sinal local detectado: {reason}."
        if motivo not in existing_reasons:
            pontos.append({
                "trecho": excerpt,
                "motivo": motivo,
                "gravidade": "MEDIA",
            })
            existing_reasons.add(motivo)
    for item in url_analysis[:3]:
        structural_score = int(item.get("score_estrutural") or 0)
        if structural_score <= 0:
            continue
        motivo = "Analise estrutural de URL detectou fatores suspeitos."
        if motivo not in existing_reasons:
            pontos.append({
                "trecho": str(item.get("url") or "")[:180],
                "motivo": motivo,
                "gravidade": "ALTA" if structural_score >= 40 else "MEDIA",
            })
            existing_reasons.add(motivo)
    adjusted["pontos_suspeitos"] = pontos[:8]

    hit_reasons = {reason for reason, _excerpt in hits}
    local_factor_map = {
        "pedido ou mencao de pagamento/transferencia": "payment_or_transfer",
        "uso de contexto bancario": "false_identity_or_authority",
        "pedido de dados ou credenciais": "auth_secret_request",
        "pressao de urgencia ou ameaca": "urgency_pressure",
        "link externo na conversa": "suspicious_link",
        "oferta ou beneficio que pode exigir acao": "reward_or_opportunity",
        "possivel impostor familiar": "false_identity_or_authority",
    }
    local_factors = list(adjusted.get("fatores_risco_identificados", []))
    for reason in hit_reasons:
        factor = local_factor_map.get(reason)
        if factor and factor not in local_factors:
            local_factors.append(factor)
    if url_analysis and "suspicious_link" not in local_factors:
        local_factors.append("suspicious_link")
    adjusted["fatores_risco_identificados"] = local_factors[:12]

    if not adjusted.get("tipo_golpe") and any(
        "bancario" in reason or "pagamento" in reason for reason in hit_reasons
    ):
        adjusted["tipo_golpe"] = "Golpe do Pix ou falso banco"

    if hits and adjusted.get("confianca_analise") == "BAIXA":
        adjusted["confianca_analise"] = "MEDIA"

    if "link externo na conversa" in hit_reasons or url_analysis:
        links = list(adjusted.get("links_ou_arquivos_suspeitos", []))
        urls = re.findall(r"https?://\S+|www\.\S+", text, flags=re.IGNORECASE)
        for url in urls[:3]:
            links.append({
                "conteudo": url.rstrip(".,;"),
                "motivo": "Link externo recebido em contexto de possivel golpe.",
            })
        existing_links = {
            str(link.get("conteudo") if isinstance(link, dict) else link)
            for link in links
        }
        for item in url_analysis[:3]:
            url = str(item.get("url") or "")
            if url and url not in existing_links:
                links.append({
                    "conteudo": url,
                    "motivo": f"Score estrutural de URL: {item.get('score_estrutural', 0)}/100.",
                    "analise_url": item,
                })
                existing_links.add(url)
        adjusted["links_ou_arquivos_suspeitos"] = links[:8]
        adjusted["acao_recomendada"] = "NAO_CLICAR"

    if "pedido de dados ou credenciais" in hit_reasons:
        dados = list(adjusted.get("dados_sensiveis_solicitados", []))
        if "outro" not in dados:
            dados.append("outro")
        adjusted["dados_sensiveis_solicitados"] = dados[:8]
        if adjusted.get("acao_recomendada") == "VERIFICAR_CANAL_OFICIAL":
            adjusted["acao_recomendada"] = "NAO_ENVIAR_DADOS"

    if "uso de contexto bancario" in hit_reasons:
        adjusted["recomendacao"] = (
            "Nao clique no link nem informe dados. Encerre o contato e confirme a situacao "
            "diretamente pelos canais oficiais do banco."
        )

    return normalize_analysis_result(adjusted)


def analyze_text(text: str, model: str = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Orquestra a analise do texto extraido.
    Retorna uma tupla: (json_resposta_da_ia, metadados_para_benchmark).
    """
    if not model:
        model = get_default_model()

    if not text.strip():
        logger.warning("Texto vazio fornecido para analise.")
        error_result = build_error_result("Nenhum texto legivel foi encontrado na imagem.")
        return error_result, {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hash_conversa": "",
            "modelo": model,
            "grupo": "INDEFINIDO",
            "tempo_resposta_ms": 0,
            "score_risco": None,
            "classificacao": "ERRO",
            "tipo_golpe": None,
            "num_pontos_suspeitos": 0,
            "num_tecnicas_identificadas": 0,
            "json_valido": False,
            "tentativas_parse": 0,
            "tokens_entrada_estimado": 0,
            "tokens_saida_estimado": 0,
            "erro": "Texto vazio ou ininteligivel",
        }

    model_lower = model.lower()
    is_openai = (
        model_lower.startswith("gpt-")
        or model_lower.startswith("o1")
        or model_lower.startswith("o3")
        or model_lower.startswith("o4")
        or model_lower.startswith("o5")
    )

    logger.info(f"Iniciando analise com modelo {model}")

    if is_openai:
        result_json, time_ms, error = analyze_with_openai(text, model)
        group = "API_EXTERNA"
    else:
        result_json, time_ms, error = analyze_with_ollama(model, text)
        group = "LOCAL"

    if error:
        result_json = build_error_result(error)
    else:
        normalized_result = normalize_analysis_result(result_json)
        enriched_result = apply_local_risk_heuristics(text, normalized_result)
        result_json = apply_deterministic_risk_score(enriched_result, text)

    has_valid_json = len(result_json) > 0 and error is None

    metadata = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hash_conversa": hashlib.md5(text.encode("utf-8")).hexdigest(),
        "modelo": model,
        "grupo": group,
        "tempo_resposta_ms": time_ms,
        "score_risco": result_json.get("score_risco", 0) if has_valid_json else None,
        "score_modelo_original": result_json.get("score_modelo_original") if has_valid_json else None,
        "classificacao": result_json.get("classificacao", "ERRO") if has_valid_json else "ERRO",
        "tipo_golpe": result_json.get("tipo_golpe"),
        "num_pontos_suspeitos": len(result_json.get("pontos_suspeitos", [])) if has_valid_json else 0,
        "num_tecnicas_identificadas": len(result_json.get("tecnicas_engenharia_social", [])) if has_valid_json else 0,
        "num_fatores_risco": len(result_json.get("fatores_risco", [])) if has_valid_json else 0,
        "json_valido": has_valid_json,
        "tentativas_parse": 1,
        "tokens_entrada_estimado": len(text) // 4,
        "tokens_saida_estimado": len(str(result_json)) // 4 if has_valid_json else 0,
        "erro": error,
    }

    if error:
        logger.error(f"Erro na analise ({model}): {error}")

    return result_json, metadata
