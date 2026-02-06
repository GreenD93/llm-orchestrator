# app/services/memory/memory_manager.py
from app.core.config import settings
from app.core.logging import setup_logger

class MemoryManager:
    def __init__(self, summarizer=None):
        self.summarizer = summarizer
        self.logger = setup_logger("MemoryManager")

    def update(self, memory: dict, user_msg: str, assistant_msg: str) -> None:
        memory["raw_history"].append({"role": "user", "content": user_msg})
        memory["raw_history"].append({"role": "assistant", "content": assistant_msg})

        if len(memory["raw_history"]) // 2 >= settings.MEMORY_MAX_RAW_TURNS:
            self._compress(memory)


    def _compress(self, memory: dict) -> None:
        if self.summarizer is None:
            return
        result = self.summarizer.summarize(memory["raw_history"])
        memory["summary_text"] = result.get("summary_text", "")
        memory["summary_struct"] = result.get("summary_struct", {})
        memory["raw_history"] = []
