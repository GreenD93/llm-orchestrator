# app/core/memory/summarizer_agent.py
import json
from typing import Any, Dict, List

from app.core.agents.base_agent import BaseAgent


def default_summarizer_prompt() -> str:
    return (
        "너는 대화 메모리 요약기다.\n"
        "입력으로 주어진 최근 대화(raw_history)를 요약해서 아래 JSON만 출력해라.\n"
        "반드시 JSON으로만 출력.\n\n"
        '출력 형식:\n{"summary_text": "간결한 텍스트 요약", "summary_struct": {"intent": "<프로젝트 정의 intent 값>", "entities": {}, "status": "IDLE", "notes": []}}\n'
    )


class SummarizerAgent(BaseAgent):
    def __init__(self, system_prompt: str | None = None, llm_config: Dict[str, Any] | None = None):
        super().__init__(
            system_prompt=system_prompt or default_summarizer_prompt(),
            llm_config=llm_config,
            stream=False,
        )

    def summarize(self, raw_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        raw = self.chat(raw_history)
        try:
            return json.loads(raw)
        except Exception:
            return {
                "summary_text": "Summary unavailable due to parsing error.",
                "summary_struct": {"intent": "", "entities": {}, "status": "IDLE", "notes": ["parse_error"]},
            }
