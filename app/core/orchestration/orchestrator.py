# app/core/orchestration/orchestrator.py
"""단일 턴 실행만 담당. Flow 결정은 Router, Agent 실행은 Handler에 위임."""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration.defaults import make_error_event
from app.core.logging import setup_logger


class CoreOrchestrator:
    """
    단일 턴 실행: session 로드 → IntentAgent → Router → Handler.run(ctx) → 저장/훅.
    manifest로 sessions, memory, runner, router, handlers, 훅 조립.

    hooks 처리 흐름:
      1. Handler가 DONE payload에 hooks: [{type, data}] 추가
      2. 프론트는 DONE 이벤트에서 hooks를 수신 (SSE/REST 공통)
      3. 서버에서 manifest["hook_handlers"][type](ctx, data) 호출
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
        self._hook_handlers: Dict[str, Any] = manifest.get("hook_handlers") or {}
        self.logger = setup_logger("CoreOrchestrator")

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

        # ── 진행 중인 플로우 감지 ──────────────────────────────────────────────
        # FILLING·READY·CONFIRMED 단계는 이미 플로우가 결정되어 있으므로 Intent 스킵.
        # 이유: LLM이 이전 봇 응답(확인 메시지 등)을 컨텍스트로 받아 시나리오 대신
        #       대화 내용을 그대로 반환하는 오탐이 간헐적으로 발생한다.
        current_scenario = getattr(state, "scenario", None)
        is_mid_flow = (
            current_scenario
            and current_scenario != "DEFAULT"
            and getattr(state, "stage", "INIT") not in ("INIT", "EXECUTED", "FAILED", "CANCELLED", "UNSUPPORTED")
        )

        # ── Intent 분류 ────────────────────────────────────────────────────────
        intent_result = {"scenario": current_scenario or "GENERAL"}

        if is_mid_flow:
            # 진행 중인 플로우 유지 — IntentAgent 호출 없음
            pass
        elif self._runner.has_agent("intent"):
            yield {"event": EventType.AGENT_START, "payload": {"agent": "intent", "label": "의도 파악 중"}}

            # retry 발생 시 AGENT_START를 다시 emit해 프론트에 재시도 중임을 알림.
            # (run()이 동기라 retry 중에는 블로킹; 완료 후 순서대로 yield됨)
            retry_events: list = []
            def _on_intent_retry(agent_name: str, attempt: int, max_retry: int, err: str) -> None:
                retry_events.append({"event": EventType.AGENT_START, "payload": {
                    "agent": agent_name,
                    "label": f"의도 재파악 중... ({attempt + 1}/{max_retry})",
                }})

            try:
                intent_result = self._runner.run("intent", ctx, on_retry=_on_intent_retry)
                for ev in retry_events:
                    yield ev
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "intent",
                    "label": "의도 파악",
                    "result": intent_result.get("scenario"),
                    "success": True,
                    "retry_count": len(retry_events),
                }}
            except Exception:
                for ev in retry_events:
                    yield ev
                # 실패 시 current_scenario 유지 (있으면) — GENERAL 폴백으로 인한 잘못된 flow 전환 방지
                intent_result = {"scenario": current_scenario or "GENERAL"}
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "intent",
                    "label": "의도 파악 재시도 후 실패",
                    "success": False,
                    "retry_count": len(retry_events),
                }}

        # ── 시나리오 전환(인터럽트) 감지 ───────────────────────────────────────
        # 진행 중인 시나리오가 있는데 다른 시나리오를 요청하면 metadata에 기록.
        # Handler 또는 후처리 훅에서 "이전 작업이 있었다"는 것을 알 수 있음.
        new_scenario = intent_result.get("scenario", "GENERAL")
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
            if final_payload:
                self._fire_hooks(ctx, final_payload)
            if final_payload and self._after_turn:
                self._after_turn(ctx, final_payload)

    def _fire_hooks(self, ctx: ExecutionContext, final_payload: dict) -> None:
        """
        DONE payload의 hooks 목록을 순회하며 등록된 서버 사이드 핸들러를 호출한다.

        handlers 예시 (manifest["hook_handlers"]):
            {
                "transfer_completed": lambda ctx, data: send_notification(data),
                "session_reset":      lambda ctx, data: log_session_end(ctx.session_id),
            }
        """
        for hook in final_payload.get("hooks", []):
            hook_type = hook.get("type")
            hook_fn = self._hook_handlers.get(hook_type)
            if hook_fn:
                try:
                    hook_fn(ctx, hook.get("data", {}))
                except Exception as e:
                    self.logger.warning(f"hook_handler '{hook_type}' error: {e}")

    def handle_stream(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        try:
            yield from self.run_one_turn(session_id, user_message)
        except Exception as e:
            yield self._on_error(e) if self._on_error else make_error_event(e)
            raise

    def handle(self, session_id: str, user_message: str) -> Dict[str, Any]:
        final = None
        for event in self.run_one_turn(session_id, user_message):
            if event.get("event") == EventType.DONE:
                final = event.get("payload")
        payload = final or {}
        return {"interaction": payload, "hooks": payload.get("hooks", [])}


class _NoopCompleted:
    def add(self, *args, **kwargs):
        pass

    def list_for_session(self, session_id: str):
        return []
