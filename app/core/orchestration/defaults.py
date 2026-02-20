# app/core/orchestration/defaults.py
"""Orchestrator 공통 기본값. manifest.py의 on_error 등에서 사용한다."""

from app.core.config import settings
from app.core.events import EventType


def make_error_event(exc: Exception | None = None) -> dict:
    """
    on_error 핸들러가 반환할 표준 에러 이벤트.
    예외 타입을 분류해 사용자에게 의미있는 메시지를 반환한다.

    사용법 (manifest.py):
        "on_error": lambda e: make_error_event(e),
    """
    payload = {
        "message": _user_message(exc),
        "next_action": "ASK",
        "ui_hint": {},
    }
    if exc and settings.DEV_MODE:
        payload["_error"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:500],
        }
    return {"event": EventType.DONE, "payload": payload}


def _user_message(exc: Exception | None) -> str:
    """예외 타입 → 사용자 친화적 메시지 변환."""
    if exc is None:
        return "처리 중 오류가 발생했어요. 다시 시도해주세요."

    # 지연 임포트 (순환 참조 방지)
    from app.core.agents.agent_runner import FatalExecutionError, RetryableError

    if isinstance(exc, RetryableError):
        msg = str(exc)
        if "unknown_scenario" in msg:
            return "의도를 파악하지 못했어요. 다시 말씀해주세요."
        if "timeout" in msg:
            return "응답 시간이 초과됐어요. 잠시 후 다시 시도해주세요."
        if "validation_failed" in msg:
            return "응답 형식이 올바르지 않아요. 다시 시도해주세요."
        return f"요청을 처리하지 못했어요. ({msg}) 다시 말씀해주세요."

    if isinstance(exc, FatalExecutionError):
        msg = str(exc).lower()
        if any(k in msg for k in ("json", "decode", "parse", "invalid")):
            return "응답을 해석하는 중 오류가 발생했어요. 다시 시도해주세요."
        if "timeout" in msg:
            return "응답 시간이 초과됐어요. 잠시 후 다시 시도해주세요."
        if "connection" in msg or "network" in msg:
            return "서버 연결에 문제가 있어요. 잠시 후 다시 시도해주세요."
        return "처리 중 오류가 발생했어요. 잠시 후 다시 시도해주세요."

    return f"예기치 않은 오류가 발생했어요. ({type(exc).__name__}) 다시 시도해주세요."
