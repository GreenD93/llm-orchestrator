# app/core/orchestration/flow_router.py
from typing import Any


class BaseFlowRouter:
    """
    intent / scenario 기반 flow 결정.
    프로젝트별로 상속하여 route() 구현.
    """

    def route(self, *, intent: str, state: Any) -> str:
        """flow 키(문자열) 반환. 예: DEFAULT_FLOW, MAIN_FLOW 등 프로젝트 정의 flow 키."""
        raise NotImplementedError
