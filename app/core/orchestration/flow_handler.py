# app/core/orchestration/flow_handler.py
"""FlowHandler: agent 실행만. run(ctx)에서 Runner로 에이전트 호출·이벤트 yield. flow 결정은 Router 담당."""

from typing import Any, Callable, Dict, Generator, Optional

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration.flow_utils import update_memory_and_save


class BaseFlowHandler:
    """
    에이전트 실행 순서·분기 로직의 유일한 위치.
    Runner.run(agent_name, ctx) 또는 Runner.run_stream(agent_name, ctx)로 에이전트 호출.
    세션·메모리 저장은 update_memory_and_save() 또는 _stream_agent_turn() 사용.
    """

    def __init__(
        self,
        runner: Any,  # AgentRunner
        sessions: Any,
        memory_manager: Any,
        state_manager_factory: Any,
        completed: Any = None,
    ):
        self.runner = runner
        self.sessions = sessions
        self.memory_manager = memory_manager
        self.state_manager_factory = state_manager_factory
        self.completed = completed

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        raise NotImplementedError

    # ── 공통 헬퍼 ─────────────────────────────────────────────────────────────

    def _stream_agent_turn(
        self,
        ctx: ExecutionContext,
        agent_name: str,
        start_label: str,
        done_label: str = "응답 완료",
        done_transform: Optional[Callable[[dict], dict]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        단일 에이전트 호출로 대화 턴을 마무리하는 공통 패턴.

        AGENT_START → 에이전트 스트리밍 → AGENT_DONE → 메모리 저장 → DONE 이벤트.

        done_transform: DONE payload에 적용할 변환 함수 (UI 정책 적용 등).
                        None이면 LLM 원본 payload에 state_snapshot만 추가.

        사용 예:
            # 단순 (minimal 등)
            yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")

            # UI 정책 적용 (transfer 등)
            yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                               done_transform=_apply_ui_policy)
        """
        yield {"event": EventType.AGENT_START, "payload": {"agent": agent_name, "label": start_label}}

        payload = None
        for ev in self.runner.run_stream(agent_name, ctx):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")

        yield {"event": EventType.AGENT_DONE, "payload": {
            "agent": agent_name, "label": done_label, "success": True,
        }}

        if payload:
            update_memory_and_save(
                self.memory_manager, self.sessions,
                ctx.session_id, ctx.state, ctx.memory,
                ctx.user_message, payload.get("message", ""),
            )

        done_payload = dict(payload or {})
        if done_transform:
            done_payload = done_transform(done_payload)
        done_payload["state_snapshot"] = (
            ctx.state.model_dump() if hasattr(ctx.state, "model_dump") else {}
        )
        yield {"event": EventType.DONE, "payload": done_payload}
