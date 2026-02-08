# app/core/memory/memory_manager.py
"""템플릿 기본은 raw_history만 관리. summarizer는 선택 플러그인(요약 필요 시 명시적 활성화)."""

from typing import Any

from app.core.config import settings
from app.core.logging import setup_logger


class MemoryManager:
    """
    - 기본: summarizer=None → raw_history만 유지, _compress()는 no-op.
    - 요약이 필요한 프로젝트는 manifest에서 SummarizerAgent를 주입해 사용.
    """

    def __init__(self, summarizer: Any = None):
        self.summarizer = summarizer
        self.logger = setup_logger("MemoryManager")

    def update(self, memory: dict, user_msg: str, assistant_msg: str) -> None:
        memory.setdefault("raw_history", []).append({"role": "user", "content": user_msg})
        memory.setdefault("raw_history", []).append({"role": "assistant", "content": assistant_msg})
        max_raw = getattr(settings, "MEMORY_MAX_RAW_TURNS", 12)
        if len(memory["raw_history"]) // 2 >= max_raw:
            self._compress(memory)

    def _compress(self, memory: dict) -> None:
        """summarizer가 없으면 no-op. 있으면 요약 후 raw_history 비우기."""
        if self.summarizer is None:
            return
        result = self.summarizer.summarize(memory.get("raw_history", []))
        memory["summary_text"] = result.get("summary_text", "")
        if "summary_struct" in result:
            memory["summary_struct"] = result["summary_struct"]
        memory["raw_history"] = []
