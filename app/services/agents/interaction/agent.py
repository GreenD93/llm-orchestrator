# app/services/agents/interaction/agent.py
import json
from app.services.agents.base_agent import BaseAgent
from app.services.events import EventType
from .prompt import SYSTEM_PROMPT

_FALLBACK = {
    "message": "응답 생성 중 오류가 발생했어요.",
    "next_action": "DONE",
    "ui_hint": {"type": "text", "fields": [], "buttons": []},
}


class InteractionAgent(BaseAgent):
    output_schema = "InteractionResult"
    supports_stream = True

    @classmethod
    def get_system_prompt(cls):
        return SYSTEM_PROMPT()

    def run(self, state, history, summary_text, summary_struct):
        raw = self.chat(self._messages(state, history, summary_text))
        return self._parse(raw)

    def run_stream(self, state, history, summary_text, summary_struct):
        buffer = ""
        for token in self.chat_stream(self._messages(state, history, summary_text)):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}

        yield {
            "event": EventType.LLM_DONE,
            "payload": self._parse(buffer),
        }

    def _messages(self, state, history, summary_text):
        return [
            {"role": "system", "content": f"State: {state.model_dump()}"},
            {"role": "system", "content": f"Summary: {summary_text}"},
            *history,
        ]

    def _parse(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except Exception:
            return _FALLBACK.copy()
