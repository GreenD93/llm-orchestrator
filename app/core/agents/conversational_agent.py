# app/core/agents/conversational_agent.py
"""
JSON {action, message} 구조를 출력하는 대화 에이전트 기본 클래스.

BaseAgent → ConversationalAgent → 프로젝트별 에이전트

## 사용법
    class MyAgent(ConversationalAgent):
        response_schema = MyOutputSchema  # Pydantic 모델 (선택)
        fallback_message = "오류가 발생했어요."

        def run(self, context, **kwargs) -> dict:
            block = f"현재 state: {context.state.stage}"
            return super().run(context, context_block=block)

        def run_stream(self, context, **kwargs):
            block = f"현재 state: {context.state.stage}"
            yield from super().run_stream(context, context_block=block)

## BaseAgent와의 차이점
- BaseAgent.run(): 미구현 (서브클래스에서 직접 구현)
- ConversationalAgent.run(): JSON 파싱 + fallback 포함한 기본 구현 제공

## minimal vs transfer 패턴 비교
- minimal/ChatAgent (BaseAgent 직접 상속): 평문 텍스트 반환, 스키마 없음, 단순 구조.
  → 빠른 프로토타이핑, 스키마가 필요 없는 서비스에 적합.
- ConversationalAgent: JSON 파싱·검증·fallback 포함.
  → 상태 기반 흐름 제어, UI action이 필요한 서비스에 적합.
"""
import json
from typing import Optional, Type

from pydantic import BaseModel

from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType


class ConversationalAgent(BaseAgent):
    """
    JSON {action, message} 구조를 출력하고 파싱·검증하는 대화 에이전트 기본 클래스.

    특징:
    - LLM 출력을 JSON으로 파싱. 실패 시 fallback 반환 (예외 propagation 없음).
    - supports_stream=True: message 필드를 char 단위로 emit → 타이핑 애니메이션.
    - response_schema 미설정 시 파싱만 수행, 스키마 검증 건너뜀.

    서브클래스에서 커스터마이징:
        response_schema  — Pydantic 모델 클래스 (선택)
        fallback_action  — 파싱 실패 시 action 값 (기본: "DONE")
        fallback_message — 파싱 실패 시 메시지
    """

    supports_stream = True
    response_schema: Optional[Type[BaseModel]] = None
    fallback_action: str = "DONE"
    fallback_message: str = "처리 중 오류가 발생했어요."

    # ── 파싱 ─────────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> dict:
        """
        LLM 출력 → {action, message} dict 파싱 + 선택적 스키마 검증.
        next_action 호환: LLM이 'action' 대신 'next_action'을 반환해도 처리한다.
        """
        try:
            data = json.loads(self._strip_markdown(raw))
            if "next_action" in data and "action" not in data:
                data["action"] = data["next_action"]
            if self.response_schema is not None:
                self.response_schema.model_validate(data)
            return data
        except Exception as e:
            self.logger.warning(
                f"[{self.__class__.__name__}] 응답 파싱 실패 ({type(e).__name__}): {str(e)[:80]} "
                f"— raw: {raw[:200]!r}"
            )
            return {"action": self.fallback_action, "message": self.fallback_message}

    # ── 기본 run / run_stream ─────────────────────────────────────────────────

    def run(self, context: ExecutionContext, context_block: str = "", **kwargs) -> dict:
        """context_block: state 정보 등 LLM 시스템 컨텍스트에 추가할 문자열."""
        messages = context.build_messages(context_block)
        return self._parse_response(self.chat(messages))

    def run_stream(self, context: ExecutionContext, context_block: str = "", **kwargs):
        """
        LLM 응답이 JSON 구조이므로 전체를 버퍼에 모은 뒤 파싱.
        파싱 후 message 필드만 char 단위로 emit → 프론트 타이핑 애니메이션 효과.
        (실시간 토큰 스트리밍이 아닌 파싱 후 순차 emit임에 유의)
        """
        messages = context.build_messages(context_block)
        buffer = ""
        for token in self.chat_stream(messages):
            buffer += token

        parsed = self._parse_response(buffer)

        for char in parsed.get("message", ""):
            yield {"event": EventType.LLM_TOKEN, "payload": char}

        yield {"event": EventType.LLM_DONE, "payload": parsed}
