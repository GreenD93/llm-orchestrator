# app/projects/transfer/agents/interaction_agent/agent.py
import json
from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType
from app.projects.transfer.agents.schemas import InteractionResult
from app.projects.transfer.agents.interaction_agent.prompt import get_system_prompt

_FALLBACK = {"action": "DONE", "message": "응답 생성 중 오류가 발생했어요."}


class InteractionAgent(BaseAgent):
    output_schema = "InteractionResult"
    supports_stream = True

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        messages = context.build_messages(f"State: {context.state.model_dump()}")
        return self._parse(self.chat(messages))

    def run_stream(self, context: ExecutionContext, **kwargs):
        messages = context.build_messages(f"State: {context.state.model_dump()}")

        # LLM 응답 전체를 버퍼에 수집 (JSON 구조이므로 파싱 후 message만 스트리밍)
        buffer = ""
        for token in self.chat_stream(messages):
            buffer += token

        parsed = self._parse(buffer)

        # action은 훅/이벤트로만 전달, 사용자에게는 message 텍스트만 스트리밍
        for char in parsed.get("message", ""):
            yield {"event": EventType.LLM_TOKEN, "payload": char}

        yield {"event": EventType.LLM_DONE, "payload": parsed}

    def _parse(self, raw: str) -> dict:
        try:
            data = json.loads(self._strip_markdown(raw))
            if "next_action" in data and "action" not in data:
                data["action"] = data["next_action"]
            InteractionResult.model_validate(data)
            return data
        except Exception:
            return _FALLBACK.copy()
