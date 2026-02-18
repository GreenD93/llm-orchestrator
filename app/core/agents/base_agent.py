# app/core/agents/base_agent.py
import json
from typing import Any, Dict, List, Optional

from app.core.logging import setup_logger
from app.core.llm.openai_client import OpenAIClient

DEFAULT_LLM_CONFIG = {"model": "gpt-4o-mini", "temperature": 0}


class BaseAgent:
    """
    Agent는 계산만 담당.
    상태 관측, 훅, 이벤트는 Executor/Orchestrator 책임.

    확장 포인트:
    - tools: BaseTool 인스턴스 리스트. card.json "tools" 필드로 주입.
      → tool_schemas()가 자동 생성되고 chat()이 tool-call 루프를 실행.
      → 파라미터가 부족하면 LLM이 사용자에게 되물어 다음 턴에 재시도.
    - retriever: search(query) → list. RAG·MCP 클라이언트 등 주입 가능.
      MCP의 경우 retriever 또는 tools에 MCP 호출을 래핑해서 등록.
    """

    output_schema: Optional[str] = None
    supports_stream: bool = False

    def __init__(
        self,
        *,
        system_prompt: str,
        llm_config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        tools: Optional[List[Any]] = None,  # List[BaseTool]
        retriever: Optional[Any] = None,
    ):
        cfg = llm_config or DEFAULT_LLM_CONFIG
        self.system_prompt = system_prompt
        self.model = cfg.get("model", "gpt-4o-mini")
        self.temperature = cfg.get("temperature", 0.0)
        self.timeout = cfg.get("timeout_sec")
        self.tools = {t.name: t for t in (tools or [])}
        self.retriever = retriever
        self.llm = OpenAIClient()
        self.logger = setup_logger(self.__class__.__name__)

    # ── Tool 확장 포인트 ──────────────────────────────────────────────────────
    def tool_schemas(self) -> List[dict]:
        """등록된 tools에서 OpenAI function-calling schema 자동 생성."""
        return [t.schema() for t in self.tools.values()]

    def _execute_tool(self, name: str, args: dict) -> str:
        """tool name으로 dispatch해서 실행."""
        tool = self.tools.get(name)
        if tool is None:
            return f"[Tool '{name}' not registered]"
        try:
            result = tool.run(**args)
            return json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        except Exception as e:
            return f"[Tool '{name}' error: {e}]"

    # ── 유틸리티 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _strip_markdown(text: str) -> str:
        """LLM이 반환하는 ```json...``` 마크다운 코드블록 제거."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            return text.strip()
        return text

    # ── LLM 호출 ─────────────────────────────────────────────────────────────
    def chat(self, messages: list) -> str:
        """
        LLM 호출. tool_schemas()가 비어있으면 단순 호출.
        tool schema가 있으면 tool-call 루프 실행:
          LLM → tool_call 반환 → 함수 실행 → 결과 전달 → LLM → ... → 최종 텍스트 반환
        """
        schemas = self.tool_schemas()
        msgs = [{"role": "system", "content": self.system_prompt}, *messages]

        while True:
            resp = self.llm.chat(
                model=self.model,
                temperature=self.temperature,
                messages=msgs,
                timeout=self.timeout,
                tools=schemas or None,
            )
            choice = resp.choices[0]

            if not getattr(choice.message, "tool_calls", None):
                return (choice.message.content or "").strip()

            msgs.append(choice.message)
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments)
                result = self._execute_tool(tc.function.name, args)
                self.logger.info(f"[tool] {tc.function.name}({args}) → {result[:120]}")
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    def chat_stream(self, messages: list):
        """스트리밍 호출. tools 미지원 (스트리밍 시 tool-call은 chat()으로 처리)."""
        return self.llm.chat_stream(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
        )

    def run(self, *args, **kwargs) -> dict:
        raise NotImplementedError

    def run_stream(self, *args, **kwargs):
        raise NotImplementedError
