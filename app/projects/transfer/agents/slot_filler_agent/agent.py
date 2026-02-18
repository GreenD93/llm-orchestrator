# app/projects/transfer/agents/slot_filler_agent/agent.py
import json
from app.core.agents.base_agent import BaseAgent, AgentPolicy
from app.core.context import ExecutionContext
from app.projects.transfer.agents.schemas import SlotResult
from app.projects.transfer.agents.slot_filler_agent.prompt import get_system_prompt


class SlotFillerAgent(BaseAgent):
    name = "slot"
    description = "슬롯 추출"
    output_type = SlotResult
    default_model = "gpt-4.1-mini"
    default_temperature = 0.0
    policy = AgentPolicy(
        max_retry=3,
        backoff_sec=1,
        validator=lambda v: isinstance(v, dict) and "operations" in v,
    )

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        raw = self.chat([{"role": "user", "content": context.user_message}]).strip()
        try:
            return json.loads(raw)
        except Exception:
            return {"operations": [], "_meta": {"parse_error": True}}
