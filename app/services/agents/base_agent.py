# app/services/agents/base_agent.py

from typing import Dict, Any
from app.services.llm.openai_client import OpenAIClient
from app.core.logging import setup_logger

DEFAULT_LLM_CONFIG = {"model": "gpt-4o-mini", "temperature": 0}


class BaseAgent:
    """
    Agent는 계산만 담당한다.
    - 상태 관측, 훅, 이벤트는 Executor/Orchestrator 책임
    """
    output_schema: str | None = None
    supports_stream: bool = False

    def __init__(
        self,
        *,
        system_prompt: str,
        llm_config: Dict[str, Any] | None = None,
        stream: bool = False,
    ):
        cfg = llm_config or DEFAULT_LLM_CONFIG
        self.system_prompt = system_prompt
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.0)
        self.timeout = cfg.get("timeout_sec")

        self.llm = OpenAIClient()
        self.logger = setup_logger(self.__class__.__name__)

    # ===== LLM helpers =====
    def chat(self, messages):
        resp = self.llm.chat(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
        )
        return resp.choices[0].message.content.strip()

    def chat_stream(self, messages):
        return self.llm.chat_stream(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
        )

    # ===== Agent interface =====
    def run(self, *args, **kwargs) -> dict:
        raise NotImplementedError

    def run_stream(self, *args, **kwargs):
        raise NotImplementedError
