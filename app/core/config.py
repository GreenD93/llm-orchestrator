# app/core/config.py
import os
from pydantic import BaseModel

class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "transfer-ai")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_FILE_NAME: str = os.getenv("LOG_FILE_NAME", "app.log")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    EXECUTION_MAX_RETRY: int = int(os.getenv("EXECUTION_MAX_RETRY", "3"))
    EXECUTION_BACKOFF_SEC: int = int(os.getenv("EXECUTION_BACKOFF_SEC", "1"))

    MEMORY_MAX_RAW_TURNS: int = int(os.getenv("MEMORY_MAX_RAW_TURNS", "12"))

    MAX_FILL_TURNS: int = int(os.getenv("MAX_FILL_TURNS", "5"))

settings = Settings()
