# app/core/memory/memory_manager.py
"""raw_history만 유지. 요약은 after_turn 훅에서 처리."""

from typing import Any

from app.core.config import settings
from app.core.logging import setup_logger


class MemoryManager:
    """enable_memory=True일 때만 히스토리 누적. 요약은 호출부(after_turn 훅)에서 처리."""

    def __init__(self, enable_memory: bool = True):
        self.enable_memory = enable_memory
        self.logger = setup_logger("MemoryManager")

    def update(self, memory: dict, user_msg: str, assistant_msg: str) -> None:
        if not self.enable_memory:
            return
        memory.setdefault("raw_history", []).append({"role": "user", "content": user_msg})
        memory.setdefault("raw_history", []).append({"role": "assistant", "content": assistant_msg})
        max_raw = getattr(settings, "MEMORY_MAX_RAW_TURNS", 12)
        if len(memory["raw_history"]) // 2 >= max_raw:
            # 마지막 N턴만 유지 (요약은 after_turn 훅에서 처리)
            memory["raw_history"] = memory["raw_history"][-(max_raw * 2) :]
