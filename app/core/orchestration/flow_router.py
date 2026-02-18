# app/core/orchestration/flow_router.py
"""Router: intent_result + state → flow 키(문자열) 반환."""

from typing import Any


class BaseFlowRouter:
    """
    프로젝트별 상속하여 route() 구현.

    확장 방법:
        SCENARIO_TO_FLOW = {
            "TRANSFER":      "TRANSFER_FLOW",
            "BALANCE_CHECK": "BALANCE_FLOW",   # ← 새 서비스: 한 줄 추가
            "GENERAL":       "DEFAULT_FLOW",
        }

    인터럽트 처리:
        route() 내부에서 state.stage 확인 → 시나리오 전환 감지 가능.
        ctx.metadata["prior_scenario"] 가 있으면 orchestrator가 전환을 감지한 것.
    """

    def route(self, *, intent_result: dict, state: Any) -> str:
        """
        intent_result: IntentAgent가 반환한 dict {"scenario": ..., "reason": ...}
        state:         현재 세션 State
        반환값:        flow 키 (예: "TRANSFER_FLOW", "DEFAULT_FLOW")
        """
        raise NotImplementedError
