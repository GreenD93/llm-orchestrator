# app/projects/transfer/agents/interaction_agent/agent.py
import json

from app.core.agents.conversational_agent import ConversationalAgent
from app.core.context import ExecutionContext
from app.projects.transfer.agents.schemas import InteractionResult
from app.projects.transfer.agents.interaction_agent.prompt import get_system_prompt


class InteractionAgent(ConversationalAgent):
    response_schema = InteractionResult
    fallback_action = "ASK"
    fallback_message = "일시적인 오류가 발생했어요. 다시 말씀해주세요."

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def _build_context_block(self, context: ExecutionContext) -> str:
        state_info = {
            "stage": context.state.stage,
            "slots": context.state.slots.model_dump(),
            "missing_required": context.state.missing_required,
            "slot_errors": context.state.meta.get("slot_errors", {}),
            "batch_total": context.state.meta.get("batch_total", 1),
            "batch_progress": context.state.meta.get("batch_progress", 0),
        }
        return f"현재 이체 상태: {json.dumps(state_info, ensure_ascii=False)}"

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        return super().run(context, context_block=self._build_context_block(context))

    def run_stream(self, context: ExecutionContext, **kwargs):
        yield from super().run_stream(context, context_block=self._build_context_block(context))
