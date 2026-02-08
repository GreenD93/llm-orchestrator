# app/core/events.py
"""스트리밍/완료 시 payload 식별용 상수만 유지. 구독/발행 없음."""

from enum import Enum


class EventType(str, Enum):
    DONE = "DONE"
    LLM_TOKEN = "LLM_TOKEN"
    LLM_DONE = "LLM_DONE"
