import keyring
from utils.logger import logger

SERVICE_NAME = "cyberdetect_openai_key"
USERNAME = "default_user"

def save_api_key(api_key: str) -> bool:
    """
    Salva a API Key da OpenAI de forma segura no Windows Credential Manager.
    """
    try:
        keyring.set_password(SERVICE_NAME, USERNAME, api_key)
        logger.info("API Key salva com sucesso no Credential Manager.")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar API Key: {e}")
        return False

def get_api_key() -> str | None:
    """
    Recupera a API Key salva, ou None se não existir.
    """
    try:
        return keyring.get_password(SERVICE_NAME, USERNAME)
    except Exception as e:
        logger.error(f"Erro ao recuperar API Key: {e}")
        return None

def delete_api_key() -> bool:
    """
    Remove a API Key do Credential Manager.
    """
    try:
        keyring.delete_password(SERVICE_NAME, USERNAME)
        logger.info("API Key removida com sucesso.")
        return True
    except keyring.errors.PasswordDeleteError:
        logger.warning("Tentativa de deletar API Key inexistente.")
        return False
    except Exception as e:
        logger.error(f"Erro ao remover API Key: {e}")
        return False

def has_api_key() -> bool:
    """
    Verifica se a API Key já está configurada.
    """
    return get_api_key() is not None
