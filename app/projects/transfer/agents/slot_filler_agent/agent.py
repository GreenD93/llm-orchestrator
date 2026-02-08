# app/projects/transfer/agents/slot_filler_agent/agent.py

import json
from app.core.agents.base_agent import BaseAgent
from app.projects.transfer.agents.slot_filler_agent.prompt import get_system_prompt


class SlotFillerAgent(BaseAgent):
    output_schema = "SlotResult"

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, user_message: str, **kwargs) -> dict:
        raw = self.chat([{"role": "user", "content": user_message}]).strip()
        try:
            return json.loads(raw)
        except Exception:
            return {"operations": [], "_meta": {"parse_error": True}}
