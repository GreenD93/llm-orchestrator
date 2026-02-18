# app/projects/transfer/agents/interaction_agent/agent.py
import json

from app.core.agents.conversational_agent import ConversationalAgent
from app.core.context import ExecutionContext
from app.projects.transfer.agents.schemas import InteractionResult
from app.projects.transfer.agents.interaction_agent.prompt import get_system_prompt


class InteractionAgent(ConversationalAgent):
    output_schema = "InteractionResult"
    response_schema = InteractionResult
    fallback_message = "응답 생성 중 오류가 발생했어요."

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        state_info = json.dumps(context.state.model_dump(), ensure_ascii=False)
        return super().run(context, context_block=f"현재 state:\n{state_info}")

    def run_stream(self, context: ExecutionContext, **kwargs):
        state_info = json.dumps(context.state.model_dump(), ensure_ascii=False)
        yield from super().run_stream(context, context_block=f"현재 state:\n{state_info}")
