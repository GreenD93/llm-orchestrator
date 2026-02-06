from typing import Literal

from app.services.state.models import Stage

FlowType = Literal["DEFAULT_FLOW", "TRANSFER_FLOW"]


class FlowRouter:
    """
    intent + state 기반으로 어떤 flow를 탈지 결정
    - 진행 중인 플로우는 intent보다 state를 우선
    """

    def route(self, *, intent: str, state) -> FlowType:
        # 🔥 이미 이체 진행 중이면 intent 무시
        if state.stage != Stage.INIT:
            return "TRANSFER_FLOW"

        if intent == "TRANSFER":
            return "TRANSFER_FLOW"

        return "DEFAULT_FLOW"
