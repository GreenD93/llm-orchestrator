# app/projects/minimal/agents/chat_agent/agent.py
"""
ChatAgent: 범용 대화 에이전트.

─── minimal 템플릿 가이드 ────────────────────────────────────────────────────
  이 파일은 새 AI 서비스를 시작하는 템플릿 예시다.
  대부분의 단순 대화 서비스는 이 패턴만으로 충분하다.

  JSON 파싱 없이 LLM의 텍스트 응답을 그대로 스트리밍한다.
  → ConversationalAgent(JSON 파싱·스키마 검증)보다 단순하고 빠름.

  복잡한 상태 머신이 필요한 경우:
  → app/projects/transfer/agents/ 를 참고해 SlotFillerAgent + StateManager 패턴으로 확장.

─── 새 서비스 확장 체크리스트 ───────────────────────────────────────────────
  1. get_system_prompt() → 서비스에 맞는 시스템 프롬프트 작성
  2. run() / run_stream() → 필요 시 context_block 추가
  3. card.json → 모델·temperature 설정
  4. manifest.py → 에이전트 등록
  5. 상태가 필요하면 → state/models.py 추가 → state_manager.py 구현
"""

from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType
from app.projects.minimal.agents.chat_agent.prompt import get_system_prompt


class ChatAgent(BaseAgent):
    """
    평문 텍스트를 스트리밍으로 반환하는 범용 대화 에이전트.

    ConversationalAgent와 달리 JSON 파싱이 없다:
    - 구조화된 출력(action, message 필드)이 불필요한 경우 사용.
    - 토큰이 생성될 때마다 즉시 yield → 더 빠른 첫 글자 응답.
    """

    supports_stream = True

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        """
        동기 실행. LLM 전체 응답을 받아 dict로 반환한다.

        context.build_messages()가 summary + raw_history + user_message를
        자동으로 포함하므로 별도 context_block 없이도 대화 맥락이 유지된다.
        """
        messages = context.build_messages()
        message = self.chat(messages)
        return {"action": "ASK", "message": message}

    def run_stream(self, context: ExecutionContext, **kwargs):
        """
        스트리밍 실행. 토큰을 실시간으로 yield하고 마지막에 LLM_DONE을 emit한다.

        ConversationalAgent와 달리 JSON 파싱이 없으므로 토큰을 버퍼에 모으지 않고
        즉시 emit한다 → 첫 글자 응답이 더 빠르다.

        Yields:
            {event: LLM_TOKEN, payload: str}  — 개별 토큰 (즉시 emit)
            {event: LLM_DONE,  payload: dict} — 전체 응답 완료 (마지막)
        """
        messages = context.build_messages()
        buffer = ""
        for token in self.chat_stream(messages):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}
        yield {"event": EventType.LLM_DONE, "payload": {"action": "ASK", "message": buffer}}
