# app/projects/minimal/agents/chat_agent/agent.py
"""
범용 대화 에이전트.
JSON 파싱 없이 LLM의 텍스트 응답을 그대로 반환한다.
복잡한 상태 머신이 필요하면 transfer 프로젝트의 SlotFillerAgent를 참고한다.
"""
from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType
from app.projects.minimal.agents.chat_agent.prompt import get_system_prompt


class ChatAgent(BaseAgent):
    supports_stream = True

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        messages = context.build_messages()  # 기본 context_block 없이도 summary+history+current 자동 포함
        message = self.chat(messages)
        return {"action": "ASK", "message": message}

    def run_stream(self, context: ExecutionContext, **kwargs):
        messages = context.build_messages()
        buffer = ""
        for token in self.chat_stream(messages):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}
        yield {"event": EventType.LLM_DONE, "payload": {"action": "ASK", "message": buffer}}
