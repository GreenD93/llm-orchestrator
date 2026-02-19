# app/core/hooks.py
"""
훅(Hook) 타입 정의.

CoreOrchestrator와 manifest에서 사용하는 콜백 시그니처를 타입으로 정의한다.
실제 훅 실행 로직은 CoreOrchestrator._fire_hooks()에 있다.

─── 훅 종류 ──────────────────────────────────────────────────────────────────
  after_turn (HookAfterTurn):
      턴 완료 후 서버사이드 콜백. 로깅·분석·알림 등 side effect에 사용.
      시그니처: (context: ExecutionContext, payload: dict) → None
      manifest["after_turn"]에 등록.

  on_error (HookOnError):
      예외 발생 시 사용자에게 반환할 DONE 이벤트를 생성하는 함수.
      시그니처: (exception: Exception) → dict (DONE payload)
      manifest["on_error"]에 등록. None이면 defaults.make_error_event() 사용.

  hook_handlers (동적 훅):
      FlowHandler가 DONE payload에 포함한 hooks 목록에 대응하는 서버사이드 핸들러.
      시그니처: (context: ExecutionContext, data: dict) → None
      manifest["hook_handlers"] = {"hook_type": fn, ...} 형태로 등록.
      프론트엔드는 DONE 이벤트의 hooks 배열을 읽어 UI 동작을 트리거한다.

  before_agent / after_agent:
      현재 미사용. 향후 에이전트 실행 전·후 공통 처리가 필요할 때 확장.

─── manifest 등록 예시 ───────────────────────────────────────────────────────
  from app.core.hooks import HookAfterTurn
  from app.core.orchestration.defaults import make_error_event

  manifest = {
      "after_turn":    lambda ctx, payload: log_turn(ctx.session_id, payload),
      "on_error":      lambda exc: make_error_event(exc),
      "hook_handlers": {
          "transfer_completed": lambda ctx, data: send_push(data["target"]),
          "session_reset":      lambda ctx, data: clear_cache(ctx.session_id),
      },
  }
"""

from typing import Any, Callable, Optional

# 훅 시그니처 타입 별칭 — manifest 작성 시 타입 힌트로 활용 가능
HookBeforeAgent = Optional[Callable[[Any, str], None]]           # (ctx, agent_name) → None
HookAfterAgent  = Optional[Callable[[Any, str, Any], None]]      # (ctx, agent_name, result) → None
HookOnError     = Optional[Callable[[Exception], dict]]          # (exc) → DONE payload
HookAfterTurn   = Optional[Callable[[Any, dict], None]]          # (ctx, payload) → None
