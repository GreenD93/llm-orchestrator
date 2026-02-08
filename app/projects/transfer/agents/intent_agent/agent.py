# app/projects/transfer/agents/intent_agent/agent.py
"""로직만. 프롬프트는 prompt.py에서 로드."""

from app.core.agents.base_agent import BaseAgent
from app.core.agents import RetryableError

from app.projects.transfer.agents.intent_agent.prompt import get_system_prompt


class IntentAgent(BaseAgent):
    output_schema = "IntentResult"

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, user_message: str, **kwargs) -> dict:
        raw = self.chat([{"role": "user", "content": user_message}])
        value = raw.strip().upper()
        if value not in ("TRANSFER", "OTHER"):
            raise RetryableError(f"invalid_intent_output: {raw}")
        supported = value == "TRANSFER"
        return {"intent": value, "supported": supported, "reason": None}
