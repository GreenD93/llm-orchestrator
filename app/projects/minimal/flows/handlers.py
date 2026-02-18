# app/projects/minimal/flows/handlers.py
from typing import Dict, Any, Generator

from app.core.context import ExecutionContext
from app.core.orchestration import BaseFlowHandler


class ChatFlowHandler(BaseFlowHandler):
    """
    단일 에이전트 대화 플로우.
    ChatAgent 실행 → 메모리 업데이트 → DONE 이벤트 반환.
    """

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")
