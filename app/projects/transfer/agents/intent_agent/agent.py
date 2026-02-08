# app/projects/transfer/agents/intent_agent/agent.py
from app.core.agents.base_agent import BaseAgent
from app.core.agents.agent_runner import RetryableError
from app.core.context import ExecutionContext
from app.projects.transfer.agents.intent_agent.prompt import get_system_prompt


class IntentAgent(BaseAgent):
    output_schema = "IntentResult"

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        raw = self.chat([{"role": "user", "content": context.user_message}])
        value = raw.strip().upper()
        if value not in ("TRANSFER", "OTHER"):
            raise RetryableError(f"invalid_intent_output: {raw}")
        supported = value == "TRANSFER"
        return {"intent": value, "supported": supported, "reason": None}
