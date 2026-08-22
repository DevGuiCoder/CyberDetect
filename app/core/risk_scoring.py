import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class RiskFactor:
    key: str
    label: str
    weight: int
    category: str
    activation: str
    cumulative: bool = False


RISK_SCORING_VERSION = "risk-factors-v1"


RISK_CLASSIFICATION_THRESHOLDS = {
    "SEGURO_MAX": 30,
    "SUSPEITO_MIN": 31,
    "SUSPEITO_MAX": 69,
    "GOLPE_MIN": 70,
}


# Tabela central do score oficial do CyberDetect. Os fatores abaixo foram
# derivados dos campos que o pipeline ja retorna: evidencias, dados sensiveis,
# links/arquivos, tecnicas de engenharia social, tipo de golpe e acao recomendada.
RISK_FACTORS: dict[str, RiskFactor] = {
    "auth_secret_request": RiskFactor(
        "auth_secret_request",
        "Pedido de senha, token ou codigo de autenticacao",
        32,
        "credenciais",
        "dados_sensiveis_solicitados contem senha, token, codigo_sms ou codigo de WhatsApp; ou evidencia textual equivalente.",
    ),
    "payment_or_transfer": RiskFactor(
        "payment_or_transfer",
        "Pedido de Pix, pagamento, boleto ou transferencia",
        26,
        "financeiro",
        "acao_recomendada NAO_PAGAR, dados_sensiveis_solicitados contem pix/dados bancarios, ou evidencias mencionam pagamento/transferencia.",
    ),
    "remote_access_or_screen_share": RiskFactor(
        "remote_access_or_screen_share",
        "Pedido de acesso remoto, instalacao de app ou compartilhamento de tela",
        34,
        "tecnico",
        "dados_sensiveis_solicitados contem acesso_remoto; links/evidencias mencionam app remoto, instalar app ou compartilhar tela.",
    ),
    "suspicious_link": RiskFactor(
        "suspicious_link",
        "Link externo ou dominio suspeito",
        22,
        "tecnico",
        "links_ou_arquivos_suspeitos contem link/dominio, acao_recomendada NAO_CLICAR, ou texto contem URL.",
    ),
    "suspicious_file": RiskFactor(
        "suspicious_file",
        "Arquivo, aplicativo ou anexo potencialmente malicioso",
        24,
        "tecnico",
        "links_ou_arquivos_suspeitos ou evidencias mencionam APK, EXE, ZIP, RAR, MSI, SCR, BAT ou arquivo/anexo suspeito.",
    ),
    "bank_card_or_document_request": RiskFactor(
        "bank_card_or_document_request",
        "Pedido de dados bancarios, cartao ou documento pessoal",
        24,
        "credenciais",
        "dados_sensiveis_solicitados contem cpf, rg, documento, selfie, cartao, dados_bancarios, endereco ou outro dado pessoal sensivel.",
    ),
    "urgency_pressure": RiskFactor(
        "urgency_pressure",
        "Urgencia artificial ou pressao temporal",
        16,
        "engenharia_social",
        "tecnicas_engenharia_social ou evidencias mencionam urgencia artificial, agora, prazo curto, bloqueio iminente ou ultima chance.",
    ),
    "threat_or_coercion": RiskFactor(
        "threat_or_coercion",
        "Ameaca, coacao, extorsao ou medo induzido",
        32,
        "engenharia_social",
        "tecnicas_engenharia_social ou evidencias mencionam medo, ameaca, prisao, multa, exposicao, sequestro, chantagem ou extorsao.",
    ),
    "false_identity_or_authority": RiskFactor(
        "false_identity_or_authority",
        "Falsa identidade, autoridade ou instituicao",
        24,
        "personificacao",
        "tecnicas_engenharia_social contem autoridade falsa/falsa identidade ou tipo/evidencia indica falso banco, suporte, governo, parente, policial, advogado ou empresa.",
    ),
    "emotional_manipulation": RiskFactor(
        "emotional_manipulation",
        "Pressao emocional, culpa, relacionamento ou familiar em perigo",
        18,
        "engenharia_social",
        "tecnicas_engenharia_social ou evidencias mencionam pressao emocional, culpa, romance, familiar, filho, acidente ou vulnerabilidade familiar.",
    ),
    "secrecy_or_isolation": RiskFactor(
        "secrecy_or_isolation",
        "Pedido de segredo ou isolamento da vitima",
        16,
        "engenharia_social",
        "tecnicas_engenharia_social ou evidencias mencionam sigilo forcado, isolamento, nao contar, nao desligar ou agir sem verificar.",
    ),
    "reward_or_opportunity": RiskFactor(
        "reward_or_opportunity",
        "Promessa de recompensa, beneficio, emprego ou oportunidade facil",
        16,
        "oportunidade",
        "tecnicas_engenharia_social, tipo de golpe ou evidencias mencionam premio, beneficio, emprego, renda extra, investimento, lucro ou recompensa.",
    ),
    "off_platform_or_unofficial_channel": RiskFactor(
        "off_platform_or_unofficial_channel",
        "Contato fora do canal oficial ou migracao de conversa",
        14,
        "canal",
        "evidencias mencionam WhatsApp/Telegram pessoal, canal nao oficial, e-mail estranho, numero desconhecido ou continuar fora da plataforma.",
    ),
    "high_severity_evidence": RiskFactor(
        "high_severity_evidence",
        "Evidencia marcada com gravidade alta",
        12,
        "evidencia",
        "pontos_suspeitos contem ao menos um item com gravidade ALTA.",
    ),
    "multiple_suspicious_points": RiskFactor(
        "multiple_suspicious_points",
        "Multiplas evidencias suspeitas independentes",
        8,
        "evidencia",
        "pontos_suspeitos contem duas ou mais evidencias normalizadas.",
    ),
    "known_scam_type": RiskFactor(
        "known_scam_type",
        "Tipo de golpe identificado",
        10,
        "contexto",
        "tipo_golpe foi preenchido pelo motor de analise.",
    ),
}


CATEGORY_CAPS = {
    "credenciais": 38,
    "financeiro": 35,
    "tecnico": 38,
    "engenharia_social": 38,
    "personificacao": 28,
    "oportunidade": 22,
    "canal": 18,
    "evidencia": 18,
    "contexto": 12,
}


FACTOR_ALIASES = {
    "senha": "auth_secret_request",
    "token": "auth_secret_request",
    "codigo": "auth_secret_request",
    "codigo_sms": "auth_secret_request",
    "codigo_whatsapp": "auth_secret_request",
    "2fa": "auth_secret_request",
    "pix": "payment_or_transfer",
    "boleto": "payment_or_transfer",
    "transferencia": "payment_or_transfer",
    "pagamento": "payment_or_transfer",
    "acesso_remoto": "remote_access_or_screen_share",
    "link": "suspicious_link",
    "arquivo": "suspicious_file",
    "urgencia artificial": "urgency_pressure",
    "medo ou ameaca": "threat_or_coercion",
    "ameaca": "threat_or_coercion",
    "autoridade falsa": "false_identity_or_authority",
    "falsa identidade": "false_identity_or_authority",
    "pressao emocional": "emotional_manipulation",
    "sigilo forcado": "secrecy_or_isolation",
    "isolamento da vitima": "secrecy_or_isolation",
    "promessa de recompensa": "reward_or_opportunity",
    "escassez": "reward_or_opportunity",
}


_PATTERNS = {
    "auth_secret_request": re.compile(r"\b(senha|token|codigo|2fa|autenticacao)\b", re.I),
    "payment_or_transfer": re.compile(r"\b(pix|boleto|transferencia|deposito|pagamento|taxa|pagar)\b", re.I),
    "remote_access_or_screen_share": re.compile(r"\b(anydesk|teamviewer|rustdesk|acesso remoto|compartilhar tela|instal(e|ar) app|instalar aplicativo)\b", re.I),
    "suspicious_link": re.compile(r"https?://|www\.|bit\.ly|tinyurl|cutt\.ly|wa\.me|t\.me", re.I),
    "suspicious_file": re.compile(r"\b(apk|exe|zip|rar|msi|scr|bat|arquivo|anexo|comprovante|nota fiscal|boleto)\b", re.I),
    "urgency_pressure": re.compile(r"\b(urgente|agora|imediatamente|ultima chance|[0-9]+\s*minutos?|bloqueio|cancelar hoje)\b", re.I),
    "threat_or_coercion": re.compile(r"\b(ameaca|prisao|multa|processo|exposicao|sequestro|chantagem|extorsao)\b", re.I),
    "false_identity_or_authority": re.compile(r"\b(falso|banco|central de seguranca|suporte|governo|policial|advogado|parente|filho|empresa)\b", re.I),
    "emotional_manipulation": re.compile(r"\b(filho|mae|pai|familiar|acidente|doenca|culpa|amor|relacionamento)\b", re.I),
    "secrecy_or_isolation": re.compile(r"\b(segredo|sigilo|nao conte|nao desligue|sem verificar)\b", re.I),
    "reward_or_opportunity": re.compile(r"\b(premio|beneficio|emprego|vaga|renda extra|lucro|investimento|recompensa)\b", re.I),
    "off_platform_or_unofficial_channel": re.compile(r"\b(telegram|whatsapp pessoal|fora da plataforma|canal oficial|email estranho|e-mail estranho|numero desconhecido)\b", re.I),
}


def _fold_text(value: Any) -> str:
    text = str(value or "")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_factor_key(value: Any) -> str:
    folded = _fold_text(value).strip()
    if folded in RISK_FACTORS:
        return folded
    return FACTOR_ALIASES.get(folded, "")


def _short_evidence(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    return (text or fallback)[:280]


def _combined_signal_text(result: Dict[str, Any], raw_text: str) -> str:
    chunks = [raw_text or ""]
    for point in _as_list(result.get("pontos_suspeitos")):
        if isinstance(point, dict):
            chunks.extend([str(point.get("trecho") or ""), str(point.get("motivo") or "")])
    for link in _as_list(result.get("links_ou_arquivos_suspeitos")):
        if isinstance(link, dict):
            chunks.extend([str(link.get("conteudo") or ""), str(link.get("motivo") or "")])
        else:
            chunks.append(str(link))
    chunks.extend(str(item) for item in _as_list(result.get("tecnicas_engenharia_social")))
    chunks.extend(str(item) for item in _as_list(result.get("dados_sensiveis_solicitados")))
    chunks.append(str(result.get("tipo_golpe") or ""))
    chunks.append(str(result.get("acao_recomendada") or ""))
    return "\n".join(chunks)


def _first_matching_evidence(text: str, pattern: re.Pattern, fallback: str) -> str:
    match = pattern.search(text or "")
    if not match:
        return fallback
    start = max(0, match.start() - 45)
    end = min(len(text), match.end() + 45)
    return _short_evidence(text[start:end], fallback)


def classify_score(score: int) -> str:
    score = max(0, min(100, int(score or 0)))
    if score >= RISK_CLASSIFICATION_THRESHOLDS["GOLPE_MIN"]:
        return "GOLPE"
    if score >= RISK_CLASSIFICATION_THRESHOLDS["SUSPEITO_MIN"]:
        return "SUSPEITO"
    return "SEGURO"


def calculate_risk_score(result: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    candidates: dict[str, dict[str, Any]] = {}
    signal_text = _combined_signal_text(result, raw_text)
    folded_signal = _fold_text(signal_text)

    def add_factor(key: str, evidence: str, source: str):
        factor = RISK_FACTORS.get(key)
        if not factor or key in candidates:
            return
        candidates[key] = {
            "fator": factor.label,
            "factor": key,
            "peso": factor.weight,
            "weight": factor.weight,
            "categoria": factor.category,
            "category": factor.category,
            "evidencia": _short_evidence(evidence, factor.activation),
            "evidence": _short_evidence(evidence, factor.activation),
            "origem": source,
            "source": source,
            "acumulativo": "Sim" if factor.cumulative else "Nao",
            "cumulative": factor.cumulative,
        }

    for item in _as_list(result.get("fatores_risco_identificados")) + _as_list(result.get("risk_factors_detected")):
        key = _normalize_factor_key(item)
        if key:
            add_factor(key, f"Fator retornado pela IA: {item}", "ia:fatores")

    sensitive = {_fold_text(item) for item in _as_list(result.get("dados_sensiveis_solicitados"))}
    if sensitive & {"senha", "token", "codigo_sms", "codigo", "codigo_whatsapp"}:
        add_factor("auth_secret_request", ", ".join(sorted(sensitive)), "ia:dados_sensiveis")
    if sensitive & {"cpf", "rg", "documento", "selfie", "cartao", "dados_bancarios", "endereco", "outro"}:
        add_factor("bank_card_or_document_request", ", ".join(sorted(sensitive)), "ia:dados_sensiveis")
    if sensitive & {"pix", "dados_bancarios"}:
        add_factor("payment_or_transfer", ", ".join(sorted(sensitive)), "ia:dados_sensiveis")
    if "acesso_remoto" in sensitive:
        add_factor("remote_access_or_screen_share", "acesso_remoto", "ia:dados_sensiveis")

    if str(result.get("acao_recomendada") or "").upper() == "NAO_PAGAR":
        add_factor("payment_or_transfer", "Acao recomendada pelo motor: NAO_PAGAR", "ia:acao")
    if str(result.get("acao_recomendada") or "").upper() == "NAO_CLICAR":
        add_factor("suspicious_link", "Acao recomendada pelo motor: NAO_CLICAR", "ia:acao")
    if str(result.get("acao_recomendada") or "").upper() == "NAO_ENVIAR_DADOS":
        add_factor("auth_secret_request", "Acao recomendada pelo motor: NAO_ENVIAR_DADOS", "ia:acao")

    links = _as_list(result.get("links_ou_arquivos_suspeitos"))
    if links:
        first_link = links[0]
        evidence = first_link.get("conteudo") if isinstance(first_link, dict) else first_link
        add_factor("suspicious_link", f"Item suspeito: {evidence}", "ia:links")
        if _PATTERNS["suspicious_file"].search(str(first_link)):
            add_factor("suspicious_file", f"Arquivo/app suspeito: {first_link}", "ia:links")

    pontos = [p for p in _as_list(result.get("pontos_suspeitos")) if isinstance(p, dict)]
    if len(pontos) >= 2:
        add_factor("multiple_suspicious_points", f"{len(pontos)} pontos suspeitos normalizados.", "ia:evidencias")
    if any(str(p.get("gravidade") or "").upper() == "ALTA" for p in pontos):
        add_factor("high_severity_evidence", "Ao menos uma evidencia foi marcada como ALTA.", "ia:evidencias")

    if result.get("tipo_golpe"):
        add_factor("known_scam_type", f"Tipo identificado: {result.get('tipo_golpe')}", "ia:tipo_golpe")

    for key, pattern in _PATTERNS.items():
        if pattern.search(folded_signal):
            add_factor(key, _first_matching_evidence(signal_text, pattern, RISK_FACTORS[key].activation), "sinais_normalizados")

    if "confianca" in folded_signal or "afinidade" in folded_signal:
        add_factor("emotional_manipulation", "Tecnica de confianca/afinidade detectada.", "sinais_normalizados")

    category_totals: dict[str, int] = {}
    applied_factors = list(candidates.values())
    for item in applied_factors:
        category = str(item["categoria"])
        category_totals[category] = category_totals.get(category, 0) + int(item["peso"])

    capped_categories = {
        category: min(total, CATEGORY_CAPS.get(category, total))
        for category, total in category_totals.items()
    }
    score_before_cap = sum(capped_categories.values())
    score = max(0, min(100, score_before_cap))

    return {
        "score": score,
        "classification": classify_score(score),
        "risk_factors": applied_factors,
        "category_totals": category_totals,
        "capped_category_totals": capped_categories,
        "score_before_global_cap": score_before_cap,
        "global_cap": 100,
        "thresholds": RISK_CLASSIFICATION_THRESHOLDS,
        "deduplication": (
            "Cada fator e aplicado no maximo uma vez por chave canonica. "
            "Fatores semanticamente relacionados compartilham categoria e respeitam limites por categoria."
        ),
    }


def apply_deterministic_risk_score(result: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    adjusted = dict(result or {})
    raw_model_score = adjusted.get("score_modelo_original", adjusted.get("score_risco", 0))
    try:
        model_score = int(float(raw_model_score or 0))
    except (TypeError, ValueError):
        model_score = 0

    assessment = calculate_risk_score(adjusted, raw_text)
    adjusted["score_modelo_original"] = max(0, min(100, model_score))
    adjusted["score_risco"] = assessment["score"]
    adjusted["classificacao"] = assessment["classification"]
    adjusted["fatores_risco"] = assessment["risk_factors"]
    adjusted["risk_factors"] = assessment["risk_factors"]
    adjusted["composicao_risco"] = {
        "score_final": assessment["score"],
        "classificacao": assessment["classification"],
        "fatores_aplicados": assessment["risk_factors"],
        "totais_por_categoria": assessment["category_totals"],
        "totais_por_categoria_com_limite": assessment["capped_category_totals"],
        "score_antes_limite_global": assessment["score_before_global_cap"],
        "limite_global": assessment["global_cap"],
        "thresholds": assessment["thresholds"],
        "deduplicacao": assessment["deduplication"],
        "score_modelo_original": adjusted["score_modelo_original"],
    }
    return adjusted


def risk_factor_table() -> Iterable[RiskFactor]:
    return RISK_FACTORS.values()
