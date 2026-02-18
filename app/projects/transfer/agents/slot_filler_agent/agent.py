# app/projects/transfer/agents/slot_filler_agent/agent.py
import json
from datetime import date

from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.projects.transfer.agents.slot_filler_agent.prompt import get_system_prompt


class SlotFillerAgent(BaseAgent):
    output_schema = "SlotResult"

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        today = date.today().isoformat()
        state_info = {
            "stage": context.state.stage,
            "slots": context.state.slots.model_dump(),
            "missing_required": context.state.missing_required,
        }
        context_block = (
            f"오늘 날짜: {today}\n"
            f"현재 이체 상태: {json.dumps(state_info, ensure_ascii=False)}"
        )
        messages = context.build_messages(context_block)
        raw = self.chat(messages)
        try:
            return json.loads(self._strip_markdown(raw))
        except Exception:
            self.logger.warning(f"[SlotFillerAgent] JSON 파싱 실패 — raw: {raw[:300]!r}")
            return {"operations": [], "_meta": {"parse_error": True}}
