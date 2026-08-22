import requests
import time
import json
from typing import Dict, Any, Tuple
from core.api_key_manager import get_api_key
from core.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from utils.logger import logger

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

def test_api_key(api_key: str, model_name: str = "gpt-4o-mini") -> bool:
    """
    Faz um teste mínimo para validar a API Key antes de salvar.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name or "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Teste"}],
        "max_tokens": 5
    }
    try:
        response = requests.post(OPENAI_ENDPOINT, headers=headers, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao testar a chave OpenAI: {e}")
        return False

def analyze_with_openai(text: str, model_name: str = "gpt-4o-mini") -> Tuple[Dict[str, Any], int, str | None]:
    """
    Envia o texto para análise no GPT-4o Mini.
    Retorna (dicionário de resposta, tempo de resposta em ms, erro_string).
    """
    api_key = get_api_key()
    if not api_key:
        return {}, 0, "API Key não configurada."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_name or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(text)}
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }

    start_time = time.time()
    try:
        response = requests.post(OPENAI_ENDPOINT, headers=headers, json=payload, timeout=30)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            try:
                # O formato json_object garante que content é parseável
                result_json = json.loads(content)
                return result_json, elapsed_ms, None
            except json.JSONDecodeError:
                return {}, elapsed_ms, "Erro ao decodificar JSON da resposta."
                
        elif response.status_code == 401:
            return {}, elapsed_ms, "API Key inválida ou expirada. Reconfigure nas configurações."
        elif response.status_code == 429:
            return {}, elapsed_ms, "Limite de requisições atingido. Aguarde alguns instantes."
        elif response.status_code >= 500:
            return {}, elapsed_ms, "Erro nos servidores da OpenAI. Tente novamente mais tarde."
        else:
            return {}, elapsed_ms, f"Erro na API HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        return {}, int((time.time() - start_time) * 1000), "Timeout: A OpenAI demorou mais de 30s para responder."
    except Exception as e:
        logger.error(f"Erro na comunicação com OpenAI: {e}")
        return {}, int((time.time() - start_time) * 1000), f"Erro interno de conexão: {str(e)}"
