# app/core/events.py
"""스트리밍/완료 시 payload 식별용 상수만 유지. 구독/발행 없음."""

from enum import Enum


class EventType(str, Enum):
    DONE = "DONE"
    LLM_TOKEN = "LLM_TOKEN"
    LLM_DONE = "LLM_DONE"
    AGENT_START = "AGENT_START"
    AGENT_DONE = "AGENT_DONE"
    TASK_PROGRESS = "TASK_PROGRESS"   # 배치 작업 진행 상황. payload: {index, total, slots}
