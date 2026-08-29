import os
from pathlib import Path
import logging

# Simple configuration management using environment variables with defaults

MAX_FILE_SIZE_BYTES = int(os.environ.get("SOVEREIGN_MAX_FILE_SIZE", 50 * 1024 * 1024)) # 50 MB
LOG_LEVEL_STR = os.environ.get("SOVEREIGN_LOG_LEVEL", "INFO").upper()

LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

DATA_DIR_PATH = os.environ.get("SOVEREIGN_DATA_DIR", "data")
DATA_DIR = Path(DATA_DIR_PATH)

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        logger.setLevel(LOG_LEVEL)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger
