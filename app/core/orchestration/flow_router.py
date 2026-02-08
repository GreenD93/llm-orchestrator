# app/core/orchestration/flow_router.py
"""모든 flow 결정 로직: intent 판별·라우팅을 명시적 조건문으로 처리. Flow 클래스/라이프사이클 없음."""

from typing import Any


class BaseFlowRouter:
    """
    intent / state 기반으로 flow 키(문자열) 반환.
    프로젝트별 상속하여 route() 구현. 조건문만 사용.
    """

    def route(self, *, intent: str, state: Any) -> str:
        """flow 키 반환. 예: DEFAULT_FLOW, TRANSFER_FLOW."""
        raise NotImplementedError
