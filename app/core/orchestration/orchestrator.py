# app/core/orchestration/orchestrator.py
"""단일 턴 실행만 담당. Flow 결정은 Router, Agent 실행은 Handler에 위임."""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration.defaults import make_error_event


class CoreOrchestrator:
    """
    단일 턴 실행: session 로드 → IntentAgent → Router → Handler.run(ctx) → 저장/훅.
    manifest로 sessions, memory, runner, router, handlers, 훅 조립.
    """

    def __init__(self, manifest: Dict[str, Any]):
        self._manifest = manifest
        self.sessions = manifest["sessions_factory"]()
        self.completed = manifest.get("completed_factory", lambda: None)()
        if self.completed is None:
            self.completed = _NoopCompleted()
        self.memory_manager = manifest["memory_manager_factory"]()
        self._runner = manifest["runner"]
        self._flow_router = manifest["flows"]["router"]()
        self._state_manager_factory = manifest["state"]["manager"]
        handlers_config = manifest["flows"]["handlers"]
        self._flow_handlers = {}
        for flow_key, handler_cls in handlers_config.items():
            self._flow_handlers[flow_key] = handler_cls(
                runner=self._runner,
                sessions=self.sessions,
                memory_manager=self.memory_manager,
                state_manager_factory=self._state_manager_factory,
                completed=self.completed,
            )
        self._default_flow = manifest.get("default_flow") or list(self._flow_handlers.keys())[0]
        self._on_error = manifest.get("on_error")
        self._after_turn = manifest.get("after_turn")

    def run_one_turn(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        """단일 턴: context 구성 → intent 분류 → flow 결정 → handler 실행 → 저장."""
        state, memory = self.sessions.get_or_create(session_id)
        ctx = ExecutionContext(
            session_id=session_id,
            user_message=user_message,
            state=state,
            memory=memory,
            metadata={},
        )

        # ── Intent 분류 ────────────────────────────────────────────────────────
        intent_result = {"scenario": "GENERAL"}
        if self._runner.has_agent("intent"):
            yield {"event": EventType.AGENT_START, "payload": {"agent": "intent", "label": "의도 파악 중"}}
            try:
                intent_result = self._runner.run("intent", ctx)
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "intent",
                    "label": "의도 파악",
                    "result": intent_result.get("scenario"),
                    "success": True,
                }}
            except Exception:
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "intent", "label": "의도 파악 실패", "success": False,
                }}

        # ── 시나리오 전환(인터럽트) 감지 ───────────────────────────────────────
        # 진행 중인 시나리오가 있는데 다른 시나리오를 요청하면 metadata에 기록.
        # Handler 또는 후처리 훅에서 "이전 작업이 있었다"는 것을 알 수 있음.
        current_scenario = getattr(state, "scenario", None)
        new_scenario = intent_result.get("scenario", "GENERAL")
        is_mid_flow = (
            current_scenario
            and current_scenario != "DEFAULT"
            and getattr(state, "stage", "INIT") not in ("INIT", "EXECUTED", "FAILED", "CANCELLED", "UNSUPPORTED")
        )
        if is_mid_flow and new_scenario != current_scenario:
            ctx.metadata["prior_scenario"] = current_scenario

        # ── Flow 결정 + 실행 ──────────────────────────────────────────────────
        flow_key = self._flow_router.route(intent_result=intent_result, state=state)
        handler = self._flow_handlers.get(flow_key) or self._flow_handlers[self._default_flow]

        final_payload = None
        try:
            for event in handler.run(ctx):
                yield event
                if event.get("event") == EventType.DONE:
                    final_payload = event.get("payload")
        finally:
            self.sessions.save_state(session_id, ctx.state)
            if final_payload and self._after_turn:
                self._after_turn(ctx, final_payload)

    def handle_stream(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        try:
            yield from self.run_one_turn(session_id, user_message)
        except Exception as e:
            yield self._on_error(e) if self._on_error else make_error_event()
            raise

    def handle(self, session_id: str, user_message: str) -> Dict[str, Any]:
        final = None
        for event in self.run_one_turn(session_id, user_message):
            if event.get("event") == EventType.DONE:
                final = event.get("payload")
        return {"interaction": final or {}, "hooks": []}


class _NoopCompleted:
    def add(self, *args, **kwargs):
        pass

    def list_for_session(self, session_id: str):
        return []
