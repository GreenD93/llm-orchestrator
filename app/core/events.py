# app/core/events.py
"""템플릿 기준: CoreOrchestrator/FlowRouter는 DONE만 필수. 스트리밍 이벤트는 프로젝트에서 선택 사용."""

from enum import Enum


class EventType(str, Enum):
    DONE = "DONE"  # 필수: 플로우 종료 시 반드시 전송
    LLM_TOKEN = "LLM_TOKEN"  # 선택: 스트리밍 토큰
    LLM_DONE = "LLM_DONE"  # 선택: 스트리밍 구간 종료
