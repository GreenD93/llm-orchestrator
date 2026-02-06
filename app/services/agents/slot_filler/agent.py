# app/services/agents/slot_filler/agent.py
import json
from app.services.agents.base_agent import BaseAgent
from .prompt import SYSTEM_PROMPT

class SlotFillerAgent(BaseAgent):
    output_schema = "SlotResult"

    @classmethod
    def get_system_prompt(cls) -> str:
        return SYSTEM_PROMPT()

    def __init__(self, *, system_prompt=None, llm_config=None, stream: bool = False):
        super().__init__(
            system_prompt=system_prompt or self.get_system_prompt(),
            llm_config=llm_config,
            stream=stream,
        )

    def run(self, user_message: str) -> dict:
        raw = self.chat([{"role": "user", "content": user_message}]).strip()
        try:
            return json.loads(raw)
        except Exception:
            # ✅ 파싱 실패 시 “아무 것도 안 함”으로 안전하게
            return {"operations": []}
