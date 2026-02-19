# app/core/agents/base_agent.py
"""
BaseAgent: 모든 Agent의 공통 기반 클래스.

─── 상속 계층 ────────────────────────────────────────────────────────────────
  BaseAgent                    ← LLM 호출 (chat/chat_stream) + Tool 루프
  ├── ConversationalAgent      ← JSON 파싱·검증·fallback·char 단위 스트리밍
  │   └── 프로젝트별 에이전트  ← 도메인 컨텍스트(state 등) 주입
  └── ChatAgent                ← 평문 텍스트 반환 (스키마 없는 단순 대화)

─── 설계 원칙 ────────────────────────────────────────────────────────────────
  - Agent는 "입력 → 출력" 계산만 담당한다.
  - 상태 변경, 훅, 이벤트 발행은 Orchestrator·FlowHandler의 책임이다.
  - Agent는 ExecutionContext를 읽기 전용으로 참조하고, 직접 수정하지 않는다.

─── 확장 포인트 ─────────────────────────────────────────────────────────────
  tools:
    BaseTool 인스턴스 리스트. card.json "tools" 필드로 외부 주입.
    tool_schemas()가 OpenAI function-calling 스키마를 자동 생성하고,
    chat()이 tool-call 루프를 실행한다.
    파라미터가 부족하면 LLM이 사용자에게 되물어 다음 턴에 재시도.

  retriever:
    search(query) → list 인터페이스. RAG·MCP 클라이언트 등을 주입 가능.
    MCP의 경우 retriever 또는 tools에 MCP 호출을 래핑해서 등록한다.

─── 새 Agent 작성 예시 ──────────────────────────────────────────────────────
  class MyAgent(BaseAgent):
      supports_stream = False

      @classmethod
      def get_system_prompt(cls) -> str:
          return "당신은 도움이 되는 어시스턴트입니다."

      def run(self, context: ExecutionContext, **kwargs) -> dict:
          messages = context.build_messages(context_block="추가 컨텍스트")
          raw = self.chat(messages)
          return {"action": "DONE", "message": raw}
"""

import json
from typing import Any, Dict, List, Optional

from app.core.logging import setup_logger
from app.core.llm.openai_client import OpenAIClient

# card.json "llm" 섹션이 없을 때 사용하는 기본값
DEFAULT_LLM_CONFIG = {"model": "gpt-4o-mini", "temperature": 0}


class BaseAgent:
    """
    LLM 호출과 Tool 실행을 담당하는 Agent 기반 클래스.

    Attributes:
        output_schema:    (미사용) 하위 호환용. response_schema를 사용할 것.
        supports_stream:  True면 run_stream() 구현 필수. AgentRunner가 확인함.
    """

    output_schema: Optional[str] = None
    supports_stream: bool = False

    def __init__(
        self,
        *,
        system_prompt: str,
        llm_config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        tools: Optional[List[Any]] = None,   # List[BaseTool]
        retriever: Optional[Any] = None,
    ):
        """
        Args:
            system_prompt: LLM system 메시지. registry.py가 get_system_prompt()로 주입.
            llm_config:    card.json "llm" 섹션 {"model": "...", "temperature": 0}.
            stream:        card.json "stream" 값. supports_stream과 별개 (현재 미사용).
            tools:         BaseTool 인스턴스 목록. build_tools()가 card.json 기반으로 생성.
            retriever:     RAG·MCP 클라이언트. chat() 내부에서 직접 활용하지 않으므로
                           run()에서 self.retriever로 참조해 수동 호출한다.
        """
        cfg = llm_config or DEFAULT_LLM_CONFIG
        self.system_prompt = system_prompt
        self.model = cfg.get("model", "gpt-4o-mini")
        self.temperature = cfg.get("temperature", 0.0)
        self.timeout = cfg.get("timeout_sec")
        # tools를 이름으로 빠르게 조회하기 위해 dict으로 변환
        self.tools = {t.name: t for t in (tools or [])}
        self.retriever = retriever
        self.llm = OpenAIClient()
        self.logger = setup_logger(self.__class__.__name__)

    # ── Tool 확장 포인트 ─────────────────────────────────────────────────────

    def tool_schemas(self) -> List[dict]:
        """등록된 tools에서 OpenAI function-calling schema를 자동 생성."""
        return [t.schema() for t in self.tools.values()]

    def _execute_tool(self, name: str, args: dict) -> str:
        """
        Tool 이름으로 dispatch 후 실행. 결과를 문자열로 반환.
        Tool이 없거나 실행 중 예외가 발생하면 오류 메시지 문자열을 반환 (예외 전파 없음).
        LLM은 이 오류 메시지를 context로 받아 사용자에게 설명할 수 있다.
        """
        tool = self.tools.get(name)
        if tool is None:
            return f"[Tool '{name}' not registered]"
        try:
            result = tool.run(**args)
            # dict/list 등은 JSON으로 직렬화해서 LLM이 읽기 쉽게 반환
            return json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        except Exception as e:
            return f"[Tool '{name}' error: {e}]"

    # ── 유틸리티 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """
        LLM이 반환하는 ```json...``` 마크다운 코드블록을 제거한다.
        JSON 파싱 전 전처리 단계로 사용.
        """
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            return text.strip()
        return text

    # ── LLM 호출 ────────────────────────────────────────────────────────────

    def chat(self, messages: list) -> str:
        """
        동기 LLM 호출. tool-call 루프를 처리한다.

        Tools가 없으면:
            messages → LLM → 텍스트 반환

        Tools가 있으면 (function-calling 루프):
            messages → LLM → tool_calls 반환
                → _execute_tool() 실행 → 결과를 messages에 추가
                → LLM → (다시 tool_calls 반환 or 최종 텍스트)
                → 최종 텍스트 반환

        Args:
            messages: ExecutionContext.build_messages()가 반환한 메시지 목록.
                      system_prompt는 여기에 자동으로 prepend된다.

        Returns:
            LLM의 최종 텍스트 응답 (strip됨).
        """
        schemas = self.tool_schemas()
        # system_prompt를 항상 첫 번째 메시지로 prepend
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

            # tool_calls가 없으면 최종 텍스트 응답 — 루프 종료
            if not getattr(choice.message, "tool_calls", None):
                return (choice.message.content or "").strip()

            # tool_calls가 있으면 각 tool을 실행하고 결과를 messages에 추가
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
            # 루프 반복 — LLM이 최종 텍스트를 반환할 때까지

    def chat_stream(self, messages: list):
        """
        스트리밍 LLM 호출. 토큰을 문자열로 yield한다.

        Notes:
            - tools를 지원하지 않는다. Tool 사용 에이전트는 chat()을 사용한다.
            - ConversationalAgent는 전체 버퍼를 수집한 뒤 JSON 파싱하므로,
              실시간 토큰 스트리밍은 사용자 타이핑 효과에만 활용된다.

        Yields:
            str: LLM이 생성한 토큰 (delta.content)
        """
        return self.llm.chat_stream(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
        )

    # ── 서브클래스 구현 포인트 ────────────────────────────────────────────────

    def run(self, *args, **kwargs) -> dict:
        """동기 실행. dict 반환. AgentRunner.run()이 호출한다."""
        raise NotImplementedError

    def run_stream(self, *args, **kwargs):
        """
        스트리밍 실행. 이벤트 dict를 yield한다.
        supports_stream=True 일 때만 AgentRunner.run_stream()이 호출한다.

        최소 구현:
            yield {"event": EventType.LLM_TOKEN, "payload": char}  # 0회 이상
            yield {"event": EventType.LLM_DONE,  "payload": dict}  # 반드시 마지막
        """
        raise NotImplementedError
