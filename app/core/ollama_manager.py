import configparser
import json
import os
import re
import time
from typing import Any, Dict, List, Tuple

import requests

from app.paths import config_file
from core.prompt_builder import LOCAL_SYSTEM_PROMPT, build_user_prompt
from utils.logger import logger


def get_ollama_base_url() -> str:
    config = configparser.ConfigParser()
    config_path = config_file()
    if os.path.exists(config_path):
        config.read(config_path)
        if "Ollama" in config and "base_url" in config["Ollama"]:
            return config["Ollama"]["base_url"].rstrip("/")
    return "http://localhost:11434"


def check_ollama_running() -> bool:
    """Verifica se o servidor do Ollama esta rodando e respondendo."""
    try:
        response = requests.get(get_ollama_base_url(), timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_installed_models() -> List[str]:
    """Retorna lista de nomes de modelos instalados no Ollama."""
    try:
        response = requests.get(f"{get_ollama_base_url()}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return [m["name"] for m in models if "name" in m]
        return []
    except requests.RequestException:
        return []


def is_model_installed(model_name: str, installed_models: List[str]) -> bool:
    if model_name in installed_models:
        return True
    if ":" not in model_name and f"{model_name}:latest" in installed_models:
        return True
    return False


def extract_json_from_text(text: str) -> str:
    """
    Tenta encontrar um bloco JSON dentro de uma string de texto livre.
    """
    text = (text or "").strip()
    if "```json" in text:
        parts = text.split("```json", 1)
        if len(parts) > 1:
            return parts[1].split("```", 1)[0].strip()
    elif "```" in text:
        parts = text.split("```", 2)
        if len(parts) > 1:
            return parts[1].strip()

    start = text.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(text[start:], start=start):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def parse_model_json(text: str) -> Dict[str, Any]:
    """
    Parse tolerante para respostas locais: remove markdown, trailing commas e texto extra.
    """
    clean_json_str = extract_json_from_text(text).strip()
    clean_json_str = re.sub(r",\s*([}\]])", r"\1", clean_json_str)

    try:
        result = json.loads(clean_json_str)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(clean_json_str)

    if not isinstance(result, dict):
        raise json.JSONDecodeError("A resposta JSON nao e um objeto", clean_json_str, 0)
    return result


def analyze_with_ollama(model_name: str, text: str) -> Tuple[Dict[str, Any], int, str | None]:
    """
    Envia a analise para um modelo local usando o Ollama.
    Retorna (dicionario_resposta, tempo_ms, erro_string).
    """
    if not check_ollama_running():
        return {}, 0, "Servidor Ollama nao esta rodando. Inicie-o e tente novamente."

    installed_models = get_installed_models()
    if installed_models and not is_model_installed(model_name, installed_models):
        return {}, 0, f"Modelo '{model_name}' nao esta instalado no Ollama."

    base_url = get_ollama_base_url()
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": LOCAL_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(text)},
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 8192,
            "num_predict": 1600,
        },
    }

    start_time = time.time()
    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=120)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 200:
            data = response.json()
            raw_content = data.get("message", {}).get("content", "")

            try:
                return parse_model_json(raw_content), elapsed_ms, None
            except json.JSONDecodeError:
                logger.error(f"Erro ao parsear JSON do Ollama ({model_name}): {raw_content[:500]}...")
                return {}, elapsed_ms, "O modelo nao retornou um formato JSON valido."

        if response.status_code == 404:
            return {}, elapsed_ms, f"Modelo '{model_name}' nao encontrado no Ollama."
        return {}, elapsed_ms, f"Erro na API do Ollama: HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        return {}, int((time.time() - start_time) * 1000), "Timeout: o modelo local demorou mais de 120s."
    except requests.RequestException as e:
        logger.error(f"Erro de conexao no OllamaManager: {e}")
        return {}, int((time.time() - start_time) * 1000), str(e)
    except Exception as e:
        logger.error(f"Erro interno no OllamaManager: {e}")
        return {}, int((time.time() - start_time) * 1000), str(e)
