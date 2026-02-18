# app/core/orchestration/defaults.py
"""
Orchestrator 공통 기본값. manifest.py의 on_error 등에서 사용한다.
"""
from app.core.events import EventType


def make_error_event(
    message: str = "처리 중 오류가 발생했어요. 다시 시도해주세요.",
) -> dict:
    """
    on_error 핸들러가 반환할 표준 에러 이벤트.

    사용법 (manifest.py):
        from app.core.orchestration.defaults import make_error_event
        "on_error": lambda e: make_error_event(),
    """
    return {
        "event": EventType.DONE,
        "payload": {
            "message": message,
            "next_action": "DONE",
            "ui_hint": {},
        },
    }
