# app/core/config.py
import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "transfer-ai")

    # 서버
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8010"))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "8501"))

    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    DEV_MODE: bool = os.getenv("DEV_MODE", "true").lower() == "true"

    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_FILE_NAME: str = os.getenv("LOG_FILE_NAME", "app.log")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    EXECUTION_MAX_RETRY: int = int(os.getenv("EXECUTION_MAX_RETRY", "3"))
    EXECUTION_BACKOFF_SEC: int = int(os.getenv("EXECUTION_BACKOFF_SEC", "1"))

    MEMORY_MAX_RAW_TURNS: int = int(os.getenv("MEMORY_MAX_RAW_TURNS", "12"))

    # 자동 요약: raw_history가 SUMMARIZE_THRESHOLD 턴 이상이면 LLM으로 요약
    MEMORY_ENABLE_SUMMARY: bool = os.getenv("MEMORY_ENABLE_SUMMARY", "true").lower() == "true"
    MEMORY_SUMMARIZE_THRESHOLD: int = int(os.getenv("MEMORY_SUMMARIZE_THRESHOLD", "6"))
    MEMORY_KEEP_RECENT_TURNS: int = int(os.getenv("MEMORY_KEEP_RECENT_TURNS", "4"))

    MEMORY_SUMMARY_MODEL: str = os.getenv("MEMORY_SUMMARY_MODEL", "gpt-4o-mini")

    MAX_FILL_TURNS: int = int(os.getenv("MAX_FILL_TURNS", "5"))


settings = Settings()
