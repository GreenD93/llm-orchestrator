# app/services/agents/intent/agent.py
from typing import Any, Dict
from app.services.agents.base_agent import BaseAgent
from app.services.execution.execution_agent import RetryableError
from .prompt import SYSTEM_PROMPT


class IntentAgent(BaseAgent):
    """
    Intent 분류 전용 Agent
    - 반드시 TRANSFER | OTHER 중 하나만 반환
    """

    output_schema = "IntentResult"

    @classmethod
    def get_system_prompt(cls) -> str:
        return SYSTEM_PROMPT()

    def __init__(self, *, system_prompt=None, llm_config=None, stream: bool = False):
        super().__init__(
            system_prompt=system_prompt or self.get_system_prompt(),
            llm_config=llm_config,
            stream=stream,
        )

    def run(self, user_message: str, **kwargs) -> dict:
        raw = self.chat([{"role": "user", "content": user_message}])
        value = raw.strip().upper()

        if value not in ("TRANSFER", "OTHER"):
            raise RetryableError(f"invalid_intent_output: {raw}")

        return {"intent": value}
