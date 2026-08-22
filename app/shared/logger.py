import logging
import os
import sys

from app.paths import logs_dir

def setup_logger():
    # Cria o diretório de logs se não existir
    log_dir = str(logs_dir())
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'cyberdetect.log')

    logger = logging.getLogger('CyberDetect')
    
    # Evita adicionar múltiplos handlers se já estiver configurado
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Handler para arquivo
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger()
