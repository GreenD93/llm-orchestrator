# app/projects/transfer/agents/interaction_agent/agent.py

import json
from app.core.agents.base_agent import BaseAgent
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

    def run(self, state, history, summary_text, summary_struct):
        raw = self.chat(self._messages(state, history, summary_text))
        return self._parse(raw)

    def run_stream(self, state, history, summary_text, summary_struct):
        buffer = ""
        for token in self.chat_stream(self._messages(state, history, summary_text)):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}
        yield {"event": EventType.LLM_DONE, "payload": self._parse(buffer)}

    def _messages(self, state, history, summary_text):
        return [
            {"role": "system", "content": f"State: {state.model_dump()}"},
            {"role": "system", "content": f"Summary: {summary_text}"},
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
