from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


URL_PATTERN = re.compile(
    r"(?P<url>(?:https?://|www\.)[^\s<>\]\)\"']+)",
    re.IGNORECASE,
)

SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "cutt.ly",
    "t.co",
    "is.gd",
    "s.id",
    "abre.ai",
    "encurta.net",
    "shorturl.at",
    "rebrand.ly",
    "wa.me",
    "t.me",
}

SENSITIVE_WORDS = {
    "login",
    "senha",
    "token",
    "pix",
    "boleto",
    "seguranca",
    "desbloqueio",
    "verificacao",
    "validacao",
    "atualizar",
    "suporte",
    "premio",
    "beneficio",
}

OFFICIAL_DOMAINS = {
    "itau": ("itau.com.br",),
    "bradesco": ("bradesco.com.br",),
    "nubank": ("nubank.com.br", "nubank.com"),
    "santander": ("santander.com.br",),
    "caixa": ("caixa.gov.br",),
    "bb": ("bb.com.br",),
    "mercadolivre": ("mercadolivre.com.br", "mercadolivre.com"),
    "gov": ("gov.br",),
    "whatsapp": ("whatsapp.com", "whatsapp.com.br"),
    "google": ("google.com", "google.com.br"),
}


@dataclass(frozen=True)
class UrlFactor:
    key: str
    label: str
    weight: int
    evidence: str
    category: str = "url"


def extract_urls(text: str) -> list[str]:
    found = []
    seen = set()
    for match in URL_PATTERN.finditer(str(text or "")):
        url = match.group("url").rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def _parse_url(url: str):
    raw = str(url or "").strip()
    normalized = raw if "://" in raw else f"http://{raw}"
    return raw, normalized, urlparse(normalized)


def _host(parsed) -> str:
    return (parsed.hostname or "").strip(".").lower()


def _registered_like_domain(host: str) -> str:
    labels = [part for part in host.split(".") if part]
    if len(labels) >= 3 and labels[-2] in {"com", "gov", "net", "org", "edu"} and labels[-1] == "br":
        return ".".join(labels[-3:])
    if len(labels) >= 2:
        return ".".join(labels[-2:])
    return host


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _port(parsed) -> int | None:
    try:
        return parsed.port
    except ValueError:
        return None


def _brand_factor(host: str, registered_domain: str) -> UrlFactor | None:
    compact_host = host.replace("-", "").replace(".", "")
    for brand, official_domains in OFFICIAL_DOMAINS.items():
        if brand not in compact_host:
            continue
        if any(host == official or host.endswith(f".{official}") for official in official_domains):
            return None
        return UrlFactor(
            "brand_impersonation",
            "Dominio menciona marca/instituicao conhecida fora do dominio oficial",
            24,
            f"{brand} em {registered_domain}",
            "personificacao",
        )
    return None


def analyze_url(url: str) -> dict[str, Any]:
    raw, normalized, parsed = _parse_url(url)
    host = _host(parsed)
    registered_domain = _registered_like_domain(host)
    labels = [part for part in host.split(".") if part]
    subdomain_count = max(0, len(labels) - (3 if registered_domain.endswith(".br") and len(labels) >= 3 else 2))
    path_and_query = f"{parsed.path or ''}?{parsed.query or ''}".strip("?")
    inspection_text = f"{host} {path_and_query}".lower()
    factors: list[UrlFactor] = []

    if parsed.scheme != "https":
        factors.append(UrlFactor("missing_https", "URL nao usa HTTPS", 10, parsed.scheme or "sem esquema", "transporte"))
    if host and _is_ip(host):
        factors.append(UrlFactor("direct_ip", "URL usa IP direto em vez de dominio", 22, host, "infraestrutura"))
    if len(raw) >= 90:
        factors.append(UrlFactor("long_url", "URL muito longa", 8, f"{len(raw)} caracteres", "ofuscacao"))
    if subdomain_count >= 3:
        factors.append(UrlFactor("many_subdomains", "Numero alto de subdominios", 12, f"{subdomain_count} subdominios", "ofuscacao"))
    if "xn--" in host:
        factors.append(UrlFactor("punycode", "Dominio usa punycode", 22, host, "homografo"))
    if registered_domain in SHORTENERS or host in SHORTENERS:
        factors.append(UrlFactor("shortener", "URL usa encurtador", 16, registered_domain, "ofuscacao"))
    if any(token in raw for token in ("@", "\\", "%00", "%2f", "%5c")):
        factors.append(UrlFactor("suspicious_chars", "URL contem caracteres de ofuscacao", 12, raw[:120], "ofuscacao"))
    sensitive_hits = sorted({word for word in SENSITIVE_WORDS if word in inspection_text})
    if sensitive_hits:
        factors.append(UrlFactor("sensitive_words", "URL contem palavras sensiveis", 10, ", ".join(sensitive_hits[:5]), "conteudo"))
    brand_factor = _brand_factor(host, registered_domain)
    if brand_factor:
        factors.append(brand_factor)
    if host.count("-") >= 3 or any(label.count("-") >= 3 for label in labels):
        factors.append(UrlFactor("excessive_hyphen", "Uso excessivo de hifens no dominio", 8, host, "ofuscacao"))
    port = _port(parsed)
    if port and port not in {80, 443}:
        factors.append(UrlFactor("uncommon_port", "URL usa porta incomum", 10, str(port), "infraestrutura"))

    score = min(100, sum(factor.weight for factor in factors))
    return {
        "url": raw,
        "normalized_url": normalized,
        "scheme": parsed.scheme,
        "host": host,
        "registered_domain": registered_domain,
        "score_estrutural": score,
        "structural_score": score,
        "fatores_encontrados": [factor.__dict__ for factor in factors],
        "factors": [factor.__dict__ for factor in factors],
        "evidencias": [factor.evidence for factor in factors],
        "observacoes": "Analise estrutural local. Nenhum acesso de rede foi realizado.",
    }


def analyze_urls_in_text(text: str) -> list[dict[str, Any]]:
    return [analyze_url(url) for url in extract_urls(text)]
