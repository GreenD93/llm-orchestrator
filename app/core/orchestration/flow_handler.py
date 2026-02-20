# app/core/orchestration/flow_handler.py
"""
FlowHandler: 에이전트 실행 순서와 분기 로직의 유일한 위치.

─── 역할 분리 ───────────────────────────────────────────────────────────────
  CoreOrchestrator → 세션 관리·Intent 분류·Router 호출·훅 실행
  FlowRouter       → intent_result + state → flow_key 결정
  FlowHandler      → flow_key에 해당하는 에이전트 파이프라인 실행  ← 여기

─── 구현 방법 ───────────────────────────────────────────────────────────────
단일 에이전트로 끝나는 단순 플로우:

    class ChatFlowHandler(BaseFlowHandler):
        def run(self, ctx):
            yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")

여러 에이전트가 연결되는 복잡 플로우:

    class TransferFlowHandler(BaseFlowHandler):
        def run(self, ctx):
            # 1. SlotFiller (동기)
            delta = self.runner.run("slot", ctx)
            # 2. StateManager (코드)
            ctx.state = self.state_manager_factory(ctx.state).apply(delta)
            yield {"event": EventType.AGENT_DONE, ...}
            # 3. 단계별 분기
            if ctx.state.stage == Stage.READY:
                ...
            else:
                # InteractionAgent (스트리밍)
                yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                                   done_transform=_apply_ui_policy)
"""

from typing import Any, Callable, Dict, Generator, Optional

from app.core.context import ExecutionContext
from app.core.events import EventType


class BaseFlowHandler:
    """
    에이전트 실행 순서·분기 로직의 유일한 위치.

    self.runner.run(agent_name, ctx)         — 동기 에이전트 실행
    self.runner.run_stream(agent_name, ctx)  — 스트리밍 에이전트 실행
    self._stream_agent_turn(...)             — 대화 턴 마무리 헬퍼 (권장)

    Attributes:
        runner:                  AgentRunner (에이전트 이름으로 실행)
        sessions:                SessionStore (세션 state 저장)
        memory_manager:          MemoryManager (대화 요약·히스토리 관리)
        state_manager_factory:   state → StateManager 팩토리 함수
        completed:               CompletedStore (완료 이력 기록)
    """

    def __init__(
        self,
        runner: Any,
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
        """
        이 플로우의 에이전트 파이프라인을 실행한다.

        반드시 EventType.DONE 이벤트를 마지막으로 yield해야 한다.
        DONE 이벤트의 payload에는 state_snapshot이 포함되어야 한다.
        """
        raise NotImplementedError

    # ── 메모리 유틸 ───────────────────────────────────────────────────────────

    def _update_memory(self, ctx: ExecutionContext, assistant_message: str) -> None:
        """
        대화 메모리 갱신 후 세션 저장.

        호출 시점: DONE 이벤트 yield 직전.
        1. memory_manager.update() — raw_history 추가, 필요 시 자동 요약
        2. sessions.save_state()  — 갱신된 state + memory 영속화
        """
        self.memory_manager.update(ctx.memory, ctx.user_message, assistant_message)
        self.sessions.save_state(ctx.session_id, ctx.state)

    # ── DONE payload 빌드 ──────────────────────────────────────────────────────

    def _build_done_payload(self, ctx: ExecutionContext, payload: dict) -> dict:
        """DONE payload에 state_snapshot을 추가한다. 수동 DONE yield 전에 호출."""
        payload["state_snapshot"] = (
            ctx.state.model_dump() if hasattr(ctx.state, "model_dump") else {}
        )
        return payload

    # ── state 리셋 ───────────────────────────────────────────────────────────

    def _reset_state(self, ctx: ExecutionContext, new_state) -> None:
        """state를 초기화하고 저장한다. memory는 건드리지 않는다."""
        ctx.state = new_state
        self.sessions.save_state(ctx.session_id, ctx.state)

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
        단일 에이전트 호출로 대화 턴을 마무리하는 공통 헬퍼.

        AGENT_START → 에이전트 스트리밍 → AGENT_DONE → 메모리 저장 → DONE

        이 헬퍼는 에이전트가 마지막 단계인 경우에만 사용한다.
        중간 단계 에이전트(SlotFiller 등)는 runner.run()을 직접 호출한다.

        Args:
            ctx:           실행 컨텍스트
            agent_name:    실행할 에이전트 키 ("chat", "interaction", ...)
            start_label:   AGENT_START 라벨 ("응답 생성 중")
            done_label:    AGENT_DONE 라벨 ("응답 완료")
            done_transform: DONE payload에 적용할 변환 함수.
                            None이면 LLM 원본 payload + state_snapshot 반환.
                            UI 정책 적용(버튼 목록 등)에 활용.

        yields:
            AGENT_START → LLM_TOKEN* → LLM_DONE → AGENT_DONE → DONE
        """
        yield {"event": EventType.AGENT_START, "payload": {"agent": agent_name, "label": start_label}}

        # 에이전트 스트리밍 — LLM_DONE 이벤트의 payload를 캡처
        payload = None
        for ev in self.runner.run_stream(agent_name, ctx):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")

        elapsed_info = {}
        if ctx.tracer and ctx.tracer.last:
            elapsed_info["elapsed_ms"] = ctx.tracer.last.elapsed_ms

        yield {"event": EventType.AGENT_DONE, "payload": {
            "agent": agent_name, "label": done_label, "success": True,
            **elapsed_info,
        }}

        # 메모리 갱신 (raw_history 추가 + 필요 시 자동 요약)
        if payload:
            self._update_memory(ctx, payload.get("message", ""))

        # DONE 이벤트 구성
        done_payload = dict(payload or {})
        if done_transform:
            done_payload = done_transform(done_payload)
        yield {"event": EventType.DONE, "payload": self._build_done_payload(ctx, done_payload)}
