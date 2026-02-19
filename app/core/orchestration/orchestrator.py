# app/core/orchestration/orchestrator.py
"""
CoreOrchestrator: 단일 턴(one-turn) 실행 파이프라인.

─── 역할 분리 ───────────────────────────────────────────────────────────────
  CoreOrchestrator → 세션 로드·IntentAgent 실행·FlowRouter·FlowHandler 조율·훅 처리
  FlowRouter       → intent_result + state → flow_key 결정
  FlowHandler      → flow_key에 해당하는 에이전트 파이프라인 실행

─── 단일 턴 실행 순서 ──────────────────────────────────────────────────────
  1. 세션 로드          sessions.get_or_create(session_id)
  2. is_mid_flow 판별   FILLING/READY/CONFIRMED → IntentAgent 스킵
  3. IntentAgent 실행   시나리오(TRANSFER, GENERAL …) 분류
  4. 시나리오 전환 감지  진행 중 시나리오 ≠ 새 시나리오 → metadata["prior_scenario"] 기록
  5. FlowRouter         flow_key 결정
  6. FlowHandler.run()  에이전트 파이프라인 실행 → 이벤트 스트리밍
  7. 세션 저장 (finally) ctx.state → sessions.save_state()
  8. 훅 실행 (finally)   _fire_hooks() — manifest["hook_handlers"] 등록 함수 호출

─── manifest 구조 ──────────────────────────────────────────────────────────
  {
      "sessions_factory":       () → SessionStore,
      "memory_manager_factory": () → MemoryManager,
      "completed_factory":      () → CompletedStore | None,   # 없으면 Noop
      "runner":                 AgentRunner,                   # 에이전트 실행기
      "flows": {
          "router":   () → FlowRouter,                        # flow_key 결정
          "handlers": {flow_key: FlowHandlerClass, ...},      # 에이전트 파이프라인
      },
      "state": {
          "manager": (state) → StateManager,                  # 상태 전이 팩토리
      },
      "default_flow":  "chat",                                # 없으면 첫 번째 handler
      "on_error":      (exc) → dict | None,                   # 에러 이벤트 생성
      "after_turn":    (ctx, payload) → None | None,          # 턴 후 서버 콜백
      "hook_handlers": {hook_type: (ctx, data) → None, ...},  # 서버사이드 훅
  }

─── hooks 처리 흐름 ────────────────────────────────────────────────────────
  FlowHandler DONE payload에 hooks 포함:
      {"hooks": [{"type": "transfer_completed", "data": {...}}]}

  CoreOrchestrator 처리:
      1. DONE 이벤트 payload의 hooks → 프론트엔드는 SSE/REST 응답에서 수신
      2. _fire_hooks() → manifest["hook_handlers"][type](ctx, data) 서버사이드 실행
"""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration.defaults import make_error_event
from app.core.logging import setup_logger


class CoreOrchestrator:
    """
    단일 턴 실행 오케스트레이터.

    manifest 딕셔너리로 모든 의존성을 주입받아 조립한다.
    비즈니스 로직은 FlowHandler에, 에이전트 실행은 AgentRunner에 위임한다.
    """

    def __init__(self, manifest: Dict[str, Any]):
        # 세션 저장소 — state·memory를 session_id 단위로 영속화
        self.sessions = manifest["sessions_factory"]()

        # 완료 이력 저장소 — 이체 완료 기록 등. 없으면 Noop 구현 사용
        self.completed = manifest.get("completed_factory", lambda: None)()
        if self.completed is None:
            self.completed = _NoopCompleted()

        # 메모리 관리자 — raw_history 추가·자동 요약
        self.memory_manager = manifest["memory_manager_factory"]()

        # 에이전트 실행기 — 이름으로 Agent를 조회·실행 (재시도·검증·타임아웃 포함)
        self._runner = manifest["runner"]

        # FlowRouter 인스턴스 — intent_result + state → flow_key
        self._flow_router = manifest["flows"]["router"]()

        # State 전이 팩토리 — (state) → StateManager. FlowHandler에 전달
        self._state_manager_factory = manifest["state"]["manager"]

        # FlowHandler 인스턴스 맵 — flow_key → handler 인스턴스
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

        # router가 알 수 없는 flow_key를 반환할 때 사용할 기본 handler
        self._default_flow = manifest.get("default_flow") or list(self._flow_handlers.keys())[0]

        # 예외 발생 시 사용자에게 반환할 DONE 이벤트를 만드는 함수
        self._on_error = manifest.get("on_error")

        # 턴 완료 후 서버사이드 콜백 (로깅·알림 등 side effect)
        self._after_turn = manifest.get("after_turn")

        # 훅 타입 → 핸들러 함수. DONE payload의 hooks 목록과 매핑
        self._hook_handlers: Dict[str, Any] = manifest.get("hook_handlers") or {}

        self.logger = setup_logger("CoreOrchestrator")

    # ── 퍼블릭 API ────────────────────────────────────────────────────────────

    def run_one_turn(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        """
        단일 턴 실행. 이벤트 스트림을 yield한다.

        실행 순서:
          세션 로드 → (IntentAgent) → FlowRouter → FlowHandler → 저장·훅
        """
        # 1. 세션에서 state·memory 로드 (없으면 새로 생성)
        state, memory = self.sessions.get_or_create(session_id)
        ctx = ExecutionContext(
            session_id=session_id,
            user_message=user_message,
            state=state,
            memory=memory,
            metadata={},
        )

        # ── 2. 진행 중인 플로우 감지 ────────────────────────────────────────
        # FILLING·READY·CONFIRMED 단계는 이미 플로우가 결정되어 있으므로 IntentAgent 스킵.
        #
        # 이유: LLM이 이전 봇 응답(예: "50만원을 홍길동에게 이체할까요?")을 context로 받아
        #       새 의도를 분류할 때 "TRANSFER"가 아닌 "GENERAL" 등을 오탐하는 경우가 있다.
        #       진행 중인 플로우는 사용자가 명시적으로 취소하기 전까지 유지한다.
        current_scenario = getattr(state, "scenario", None)
        is_mid_flow = (
            current_scenario
            and current_scenario != "DEFAULT"
            and getattr(state, "stage", "INIT") not in ("INIT", "EXECUTED", "FAILED", "CANCELLED", "UNSUPPORTED")
        )

        # ── 3. IntentAgent 실행 ─────────────────────────────────────────────
        intent_result = {"scenario": current_scenario or "GENERAL"}

        if is_mid_flow:
            # 진행 중인 플로우 유지 — IntentAgent 호출 없음
            pass
        elif self._runner.has_agent("intent"):
            yield {"event": EventType.AGENT_START, "payload": {"agent": "intent", "label": "의도 파악 중"}}

            # retry 발생 시 AGENT_START를 다시 emit해 프론트에 재시도 중임을 알린다.
            # run()이 동기 블로킹이므로 retry 이벤트는 실행 완료 후 순서대로 yield됨.
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
                # 실패 시 current_scenario 유지 — GENERAL 폴백으로 인한 잘못된 flow 전환 방지
                intent_result = {"scenario": current_scenario or "GENERAL"}
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "intent",
                    "label": "의도 파악 재시도 후 실패",
                    "success": False,
                    "retry_count": len(retry_events),
                }}

        # ── 4. 시나리오 전환(인터럽트) 감지 ─────────────────────────────────
        # 진행 중인 시나리오가 있는데 다른 시나리오를 요청하면 metadata에 기록.
        # FlowHandler 또는 after_turn 훅에서 "이전 작업이 있었다"는 것을 알 수 있다.
        new_scenario = intent_result.get("scenario", "GENERAL")
        if is_mid_flow and new_scenario != current_scenario:
            ctx.metadata["prior_scenario"] = current_scenario

        # ── 5·6. Flow 결정 + Handler 실행 ────────────────────────────────────
        flow_key = self._flow_router.route(intent_result=intent_result, state=state)
        handler = self._flow_handlers.get(flow_key) or self._flow_handlers[self._default_flow]

        final_payload = None
        try:
            for event in handler.run(ctx):
                yield event
                if event.get("event") == EventType.DONE:
                    final_payload = event.get("payload")
        finally:
            # 7. 세션 저장 — 예외가 발생해도 반드시 실행
            self.sessions.save_state(session_id, ctx.state)
            # 8. 훅 실행 — DONE payload가 있을 때만
            if final_payload:
                self._fire_hooks(ctx, final_payload)
            if final_payload and self._after_turn:
                self._after_turn(ctx, final_payload)

    def _fire_hooks(self, ctx: ExecutionContext, final_payload: dict) -> None:
        """
        DONE payload의 hooks 목록을 순회하며 manifest에 등록된 서버사이드 핸들러를 호출한다.

        훅 핸들러 예시 (manifest["hook_handlers"]):
            {
                "transfer_completed": lambda ctx, data: send_push_notification(data),
                "session_reset":      lambda ctx, data: log_session_end(ctx.session_id),
            }

        DONE payload 예시:
            {
                "message": "이체가 완료됐어요.",
                "hooks": [
                    {"type": "transfer_completed", "data": {"amount": 50000, "target": "홍길동"}},
                ]
            }

        훅 실행 중 예외가 발생해도 무시 (로그만 남김). 메인 응답에는 영향 없음.
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
        """
        SSE 스트리밍 엔드포인트용 래퍼.
        예외 발생 시 on_error 핸들러로 DONE 에러 이벤트를 emit하고 re-raise한다.
        """
        try:
            yield from self.run_one_turn(session_id, user_message)
        except Exception as e:
            yield self._on_error(e) if self._on_error else make_error_event(e)
            raise

    def handle(self, session_id: str, user_message: str) -> Dict[str, Any]:
        """
        비스트리밍(REST) 엔드포인트용 래퍼.
        DONE 이벤트의 payload를 반환한다.

        Returns:
            {"interaction": <DONE payload>, "hooks": [<hook list>]}
        """
        final = None
        for event in self.run_one_turn(session_id, user_message):
            if event.get("event") == EventType.DONE:
                final = event.get("payload")
        payload = final or {}
        return {"interaction": payload, "hooks": payload.get("hooks", [])}


class _NoopCompleted:
    """CompletedStore가 없을 때 사용하는 무동작 구현체."""

    def add(self, *args, **kwargs):
        pass

    def list_for_session(self, session_id: str):
        return []
