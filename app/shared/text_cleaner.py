import re

def clean_ocr_text(text: str) -> str:
    """
    Limpa e normaliza o texto extraído pelo OCR, removendo ruídos
    comuns enquanto mantém a legibilidade da conversa.
    """
    if not text:
        return ""
        
    # Remove caracteres de controle estranhos, mas mantém quebras de linha
    cleaned = re.sub(r'[^\x20-\x7E\xC0-\xFF\n\r]', '', text)
    
    # Remove múltiplos espaços em branco (mantendo as quebras de linha normais)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    
    # Remove quebras de linha excessivas (mais de 2 vira 2)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    return cleaned.strip()
