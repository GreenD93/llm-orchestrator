# app/services/memory/summarizer_agent.py
import json
from app.services.agents.base_agent import BaseAgent
from .prompts import SUMMARIZER_SYSTEM_PROMPT


class SummarizerAgent(BaseAgent):
    def __init__(self, llm_config=None):
        super().__init__(
            system_prompt=SUMMARIZER_SYSTEM_PROMPT(),
            llm_config=llm_config,
            stream=False,
        )

    def summarize(self, raw_history: list[dict]) -> dict:
        raw = self.chat(raw_history)
        try:
            return json.loads(raw)
        except Exception:
            # 최악의 경우 fallback
            return {
                "summary_text": "Summary unavailable due to parsing error.",
                "summary_struct": {"intent": "OTHER", "entities": {"target": None, "amount": None}, "status": "IDLE", "notes": ["parse_error"]},
            }
