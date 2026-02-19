# app/core/agents/conversational_agent.py
"""
JSON {action, message} 구조를 출력하는 대화 에이전트 기본 클래스.

─── 상속 계층 ────────────────────────────────────────────────────────────────
  BaseAgent                    ← LLM 호출 (chat/chat_stream)
  └── ConversationalAgent      ← JSON 파싱·검증·fallback·char 단위 스트리밍
      └── 프로젝트별 에이전트  ← 도메인 컨텍스트(state 등) 주입

─── 스트리밍 동작 방식 ──────────────────────────────────────────────────────
  JSON 구조체를 스트리밍하면 파싱이 불가능하므로:
  1. LLM 토큰을 전체 버퍼에 수집 (실시간 emit 안 함)
  2. 버퍼 파싱 → message 필드 추출
  3. message를 글자(char) 단위로 emit → 프론트에서 타이핑 애니메이션 효과

  (실시간 토큰 스트리밍이 아닌 파싱 후 순차 emit임에 주의)

─── 새 서비스에서 사용하기 ─────────────────────────────────────────────────
  class MyAgent(ConversationalAgent):
      response_schema = MyOutputSchema  # Pydantic 모델 (선택)
      fallback_message = "오류가 발생했어요."

      def run(self, context, **kwargs) -> dict:
          block = f"현재 state: {context.state.stage}"
          return super().run(context, context_block=block)

      def run_stream(self, context, **kwargs):
          block = f"현재 state: {context.state.stage}"
          yield from super().run_stream(context, context_block=block)

─── ChatAgent와의 차이 ─────────────────────────────────────────────────────
  ConversationalAgent:   JSON 파싱·검증·fallback 포함. 상태 기반 서비스에 적합.
  ChatAgent(BaseAgent):  평문 텍스트 반환. 스키마 없는 단순 대화에 적합.
"""

import json
from typing import Optional, Type

from pydantic import BaseModel

from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType


class ConversationalAgent(BaseAgent):
    """
    JSON {action, message} 구조를 출력하는 대화 에이전트 기본 클래스.

    서브클래스에서 커스터마이징:
        response_schema  — Pydantic 모델 클래스. 설정하면 파싱 결과를 검증.
                           검증 실패 시 fallback 반환 (예외 propagation 없음).
        fallback_action  — 파싱 실패 시 action 값 (기본: "DONE")
        fallback_message — 파싱 실패 시 메시지. 사용자에게 보여지는 오류 문구.
    """

    supports_stream = True

    # ── 서브클래스 커스터마이징 포인트 ────────────────────────────────────────
    response_schema: Optional[Type[BaseModel]] = None
    fallback_action:  str = "DONE"
    fallback_message: str = "처리 중 오류가 발생했어요."

    # ── 파싱 ─────────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> dict:
        """
        LLM 출력 → {action, message} dict 파싱.

        처리 순서:
          1. 마크다운 코드블록 제거 (```json ... ```)
          2. JSON 파싱
          3. 'next_action' 하위 호환: LLM이 'action' 대신 'next_action'을 반환해도 처리
          4. response_schema가 있으면 Pydantic 검증
          5. 파싱·검증 실패 시 fallback dict 반환 (예외 전파 없음)
        """
        try:
            data = json.loads(self._strip_markdown(raw))
            # 'next_action' → 'action' 하위 호환 처리
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
        """
        동기 실행. LLM 응답을 파싱해 dict 반환.

        Args:
            context_block: state 정보 등 동적 컨텍스트. system 메시지 앞에 추가됨.
        """
        messages = context.build_messages(context_block)
        return self._parse_response(self.chat(messages))

    def run_stream(self, context: ExecutionContext, context_block: str = "", **kwargs):
        """
        스트리밍 실행.
        LLM 응답 전체를 버퍼에 모은 뒤 파싱 → message 필드를 글자 단위로 emit.

        yields:
            {"event": LLM_TOKEN, "payload": char}  ← message 글자 단위
            {"event": LLM_DONE,  "payload": dict}  ← 파싱된 전체 결과
        """
        messages = context.build_messages(context_block)
        buffer = ""
        for token in self.chat_stream(messages):
            buffer += token
        # 전체 버퍼 파싱 후 message 필드 글자 단위 emit
        parsed = self._parse_response(buffer)
        for char in parsed.get("message", ""):
            yield {"event": EventType.LLM_TOKEN, "payload": char}
        yield {"event": EventType.LLM_DONE, "payload": parsed}
