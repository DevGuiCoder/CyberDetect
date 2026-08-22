from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from PIL import Image

from core.risk_scoring import apply_deterministic_risk_score
from core.url_analyzer import analyze_url, extract_urls


PIX_MARKERS = (
    "br.gov.bcb.pix",
    "pix",
    "chave pix",
    "copia e cola",
    "payload pix",
)


@lru_cache(maxsize=1)
def _opencv_modules():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        return cv2, np, ""
    except Exception as exc:
        return None, None, str(exc)


def _preview(value: Any, limit: int = 700) -> str:
    return " ".join(str(value or "").split())[:limit]


def _is_pix_payload(value: str) -> bool:
    folded = value.lower()
    return any(marker in folded for marker in PIX_MARKERS) or bool(
        re.search(r"\b000201\d{4,}.*br\.gov\.bcb\.pix", folded, re.I)
    )


def _content_kind(value: str) -> str:
    if extract_urls(value):
        return "url"
    if _is_pix_payload(value):
        return "pix"
    return "text"


def decode_qr_codes(image: Image.Image) -> dict[str, Any]:
    cv2, np, error = _opencv_modules()
    if cv2 is None or np is None:
        return {
            "available": False,
            "values": [],
            "error": f"Detector QR indisponivel: {error}",
            "engine": "opencv",
        }

    try:
        rgb = image.convert("RGB")
        array = np.array(rgb)
        detector = cv2.QRCodeDetector()
        ok, decoded_info, _points, _straight = detector.detectAndDecodeMulti(array)
        if ok and decoded_info:
            values = [str(item) for item in decoded_info if str(item or "").strip()]
        else:
            value, _points, _straight = detector.detectAndDecode(array)
            values = [str(value)] if str(value or "").strip() else []
        deduped = list(dict.fromkeys(values))
        return {"available": True, "values": deduped, "error": "", "engine": "opencv"}
    except Exception as exc:
        return {"available": True, "values": [], "error": str(exc), "engine": "opencv"}


def analyze_qr_values(values: list[str]) -> list[dict[str, Any]]:
    items = []
    for index, value in enumerate(values, start=1):
        raw = str(value or "").strip()
        if not raw:
            continue
        kind = _content_kind(raw)
        urls = extract_urls(raw)
        url_analysis = [analyze_url(url) for url in urls]
        is_pix = kind == "pix" or _is_pix_payload(raw)
        structural_score = max([int(item.get("score_estrutural") or 0) for item in url_analysis] or [0])
        score = min(100, structural_score + (28 if is_pix else 0))
        factors = []
        if urls:
            factors.append({
                "key": "qr_url",
                "label": "QR Code contem URL",
                "weight": 12,
                "evidence": urls[0],
                "category": "qr",
            })
        if is_pix:
            factors.append({
                "key": "qr_pix",
                "label": "QR Code contem conteudo financeiro/PIX",
                "weight": 28,
                "evidence": "PIX detectado no conteudo do QR",
                "category": "financeiro",
            })
        items.append({
            "id": f"qr-{index}",
            "content": raw,
            "content_preview": _preview(raw),
            "kind": kind,
            "is_url": bool(urls),
            "is_pix": is_pix,
            "urls": urls,
            "url_analysis": url_analysis,
            "score_estrutural": score,
            "structural_score": score,
            "fatores_encontrados": factors,
            "factors": factors,
            "observacoes": "QR analisado localmente. Nenhum link foi aberto automaticamente.",
        })
    return items


def analyze_qr_codes(image: Image.Image) -> dict[str, Any]:
    decoded = decode_qr_codes(image)
    return {
        **decoded,
        "items": analyze_qr_values(decoded.get("values") or []),
    }


def build_qr_analysis_text(ocr_text: str, qr_analysis: dict[str, Any]) -> str:
    parts = [str(ocr_text or "").strip()]
    items = qr_analysis.get("items") or []
    for item in items:
        kind = str(item.get("kind") or "text").upper()
        parts.append(f"[QR_CODE {kind}] {item.get('content_preview') or item.get('content') or ''}")
    return "\n\n".join(part for part in parts if part).strip()


def apply_qr_analysis_to_result(
    result: dict[str, Any],
    qr_analysis: dict[str, Any],
    raw_text: str = "",
) -> dict[str, Any]:
    items = qr_analysis.get("items") or []
    if not items:
        return result

    adjusted = dict(result or {})
    adjusted["qr_analysis"] = items[:8]
    adjusted["analise_qr"] = items[:8]

    pontos = list(adjusted.get("pontos_suspeitos") or [])
    fatores = list(adjusted.get("fatores_risco_identificados") or [])
    links = list(adjusted.get("links_ou_arquivos_suspeitos") or [])

    for item in items[:5]:
        content = str(item.get("content_preview") or item.get("content") or "")
        if item.get("is_pix"):
            pontos.append({
                "trecho": content[:240],
                "motivo": "QR Code contem conteudo financeiro/PIX.",
                "gravidade": "ALTA",
            })
            if "payment_or_transfer" not in fatores:
                fatores.append("payment_or_transfer")
            if not adjusted.get("tipo_golpe"):
                adjusted["tipo_golpe"] = "QR Code financeiro/PIX"
            if adjusted.get("acao_recomendada") in {None, "", "IGNORAR", "VERIFICAR_CANAL_OFICIAL"}:
                adjusted["acao_recomendada"] = "NAO_PAGAR"

        if item.get("is_url"):
            pontos.append({
                "trecho": content[:240],
                "motivo": "QR Code contem URL. A URL foi analisada estruturalmente sem acesso de rede.",
                "gravidade": "ALTA" if int(item.get("score_estrutural") or 0) >= 40 else "MEDIA",
            })
            if "suspicious_link" not in fatores:
                fatores.append("suspicious_link")
            if adjusted.get("acao_recomendada") != "NAO_PAGAR":
                adjusted["acao_recomendada"] = "NAO_CLICAR"
            for url in item.get("urls") or []:
                links.append({
                    "conteudo": url,
                    "motivo": "URL extraida de QR Code. Nenhum link foi aberto automaticamente.",
                    "analise_url": (item.get("url_analysis") or [{}])[0],
                })

    adjusted["pontos_suspeitos"] = pontos[:8]
    adjusted["fatores_risco_identificados"] = fatores[:12]
    adjusted["links_ou_arquivos_suspeitos"] = links[:8]
    return apply_deterministic_risk_score(adjusted, raw_text)
