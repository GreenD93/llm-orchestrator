import json
from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType
from app.projects.minimal.agents.schemas import InteractionResult
from app.projects.minimal.agents.interaction_agent.prompt import get_system_prompt

_FALLBACK = {"action": "DONE", "message": "응답 생성 중 오류가 발생했어요."}


class InteractionAgent(BaseAgent):
    output_schema = "InteractionResult"
    supports_stream = True

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        history = context.get_history()
        summary_text = context.memory.get("summary_text", "")
        raw = self.chat(self._messages(context.state, history, summary_text))
        return self._parse(raw)

    def run_stream(self, context: ExecutionContext, **kwargs):
        history = context.get_history()
        summary_text = context.memory.get("summary_text", "")
        buffer = ""
        for token in self.chat_stream(self._messages(context.state, history, summary_text)):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}
        yield {"event": EventType.LLM_DONE, "payload": self._parse(buffer)}

    def _messages(self, state, history, summary_text):
        return [
            {"role": "system", "content": f"State: {state.model_dump() if hasattr(state, 'model_dump') else state}"},
            *history,
        ]

    def _parse(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
            if "next_action" in data and "action" not in data:
                data["action"] = data["next_action"]
            InteractionResult.model_validate(data)
            return data
        except Exception:
            return _FALLBACK.copy()
