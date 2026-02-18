# app/core/state/base_state.py
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class BaseState(BaseModel):
    """
    모든 시나리오 공통 State (도메인 무관).

    task_queue: 순차 처리할 작업 목록. 서비스 정의 없이 사용 가능.
        - 각 항목은 해당 서비스의 slot dict (부분 입력 허용)
        - 완전한 항목 → 즉시 실행
        - 불완전한 항목 → InteractionAgent가 부족한 정보 요청 후 진행
        - 새 서비스 지원: FlowHandler에서 pop 후 slot 적용만 하면 됨
    """
    scenario: str = "DEFAULT"
    stage: str = "INIT"
    meta: Dict[str, Any] = Field(default_factory=dict)
    task_queue: List[Dict[str, Any]] = Field(default_factory=list)
