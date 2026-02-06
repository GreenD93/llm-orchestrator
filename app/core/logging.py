# app/core/logging.py
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from app.core.config import settings

_LOGGERS = {}

def setup_logger(name: str) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(settings.LOG_LEVEL)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)

    os.makedirs(settings.LOG_DIR, exist_ok=True)
    fh = TimedRotatingFileHandler(
        os.path.join(settings.LOG_DIR, settings.LOG_FILE_NAME),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)

    # 중복 핸들러 방지
    if not logger.handlers:
        logger.addHandler(sh)
        logger.addHandler(fh)

    logger.propagate = False
    _LOGGERS[name] = logger
    return logger
