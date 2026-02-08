# app/projects/transfer/flows/router.py
from typing import Literal
from app.core.orchestration import BaseFlowRouter
from app.projects.transfer.state.models import TransferState

FlowType = Literal["DEFAULT_FLOW", "TRANSFER_FLOW"]


class TransferFlowRouter(BaseFlowRouter):
    """시나리오 + intent 기반 flow 결정. 진행 중인 시나리오는 intent보다 scenario 우선."""

    def route(self, *, intent: str, state: TransferState) -> str:
        if getattr(state, "scenario", None) == "TRANSFER":
            return "TRANSFER_FLOW"
        if intent == "TRANSFER":
            return "TRANSFER_FLOW"
        return "DEFAULT_FLOW"
