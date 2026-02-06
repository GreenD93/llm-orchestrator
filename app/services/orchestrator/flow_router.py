from typing import Literal
from app.services.state.models import Stage

FlowType = Literal["DEFAULT_FLOW", "TRANSFER_FLOW"]


class FlowRouter:
    """
    scenario + intent 기반 flow 결정
    - 진행 중인 시나리오는 intent보다 scenario 우선
    """

    def route(self, *, intent: str, state) -> FlowType:
        if getattr(state, "scenario", None) == "TRANSFER":
            return "TRANSFER_FLOW"

        if intent == "TRANSFER":
            return "TRANSFER_FLOW"

        return "DEFAULT_FLOW"
