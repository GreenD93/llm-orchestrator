# app/projects/transfer/agents/intent_agent/agent.py
from app.core.agents.base_agent import BaseAgent, AgentPolicy
from app.core.agents.agent_runner import RetryableError
from app.core.context import ExecutionContext
from app.projects.transfer.agents.schemas import IntentResult
from app.projects.transfer.agents.intent_agent.prompt import get_system_prompt


class IntentAgent(BaseAgent):
    name = "intent"
    description = "사용자 발화의 의도 분류"
    output_type = IntentResult
    default_model = "gpt-4.1-mini"
    default_temperature = 0.0
    policy = AgentPolicy(
        max_retry=2,
        backoff_sec=1,
        timeout_sec=6,
        validator=lambda v: (
            isinstance(v, dict)
            and v.get("intent") in ("TRANSFER", "OTHER")
            and "supported" in v
        ),
    )

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
