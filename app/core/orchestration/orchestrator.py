# app/core/orchestration/orchestrator.py
"""단일 턴 실행만 담당. Flow 결정은 Router, Agent 실행은 Handler에 위임."""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType


class CoreOrchestrator:
    """
    단일 턴 실행: session 로드 → Router로 flow 결정 → Handler.run(ctx) → 저장/훅.
    manifest로 sessions, memory, runner, router, handlers, 훅 조립.
    """

    def __init__(self, manifest: Dict[str, Any]):
        self._manifest = manifest
        self.sessions = manifest["sessions_factory"]()
        self.completed = manifest.get("completed_factory", lambda: None)()
        if self.completed is None:
            self.completed = _NoopCompleted()
        self.memory_manager = manifest["memory_manager_factory"]()
        self._runner = manifest["runner"]  # AgentRunner
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
        """단일 턴: context 구성 → flow 결정 → handler 실행 → 저장."""
        state, memory = self.sessions.get_or_create(session_id)
        ctx = ExecutionContext(
            session_id=session_id,
            user_message=user_message,
            state=state,
            memory=memory,
            metadata={},
        )

        # Flow 결정: intent 실행(있으면) 후 Router
        intent = "OTHER"
        if "intent" in self._runner._agents:
            try:
                intent_result = self._runner.run("intent", ctx)
                intent = intent_result.get("intent", "OTHER")
                supported = intent_result.get("supported", True)
                if not supported:
                    flow_key = self._default_flow
                else:
                    flow_key = self._flow_router.route(intent=intent, state=state)
            except Exception:
                flow_key = self._default_flow
        else:
            flow_key = self._flow_router.route(intent=intent, state=state)

        handler = self._flow_handlers.get(flow_key) or self._flow_handlers[self._default_flow]
        final_payload = None
        try:
            for event in handler.run(ctx):
                yield event
                if event.get("event") == EventType.DONE:
                    final_payload = event.get("payload")
        finally:
            state, memory = ctx.state, ctx.memory
            self.sessions.save_state(session_id, state)
            if final_payload and self._after_turn:
                self._after_turn(ctx, final_payload)

    def handle_stream(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        try:
            yield from self.run_one_turn(session_id, user_message)
        except Exception as e:
            if self._on_error:
                yield self._on_error(e)
            else:
                yield {
                    "event": EventType.DONE,
                    "payload": {
                        "message": "처리 중 오류가 발생했어요. 다시 시도해주세요.",
                        "next_action": "DONE",
                        "ui_hint": {"type": "text", "fields": [], "buttons": []},
                    },
                }
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
