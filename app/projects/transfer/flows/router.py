# app/projects/transfer/flows/router.py
from app.core.orchestration import BaseFlowRouter
from app.projects.transfer.state.models import Stage, TERMINAL_STAGES, TransferState


class TransferFlowRouter(BaseFlowRouter):
    """
    시나리오 → flow 키 매핑.

    새 서비스 추가:
        1. IntentAgent.KNOWN_SCENARIOS에 값 추가
        2. intent_agent/prompt.py에 분류 기준 추가
        3. 여기 SCENARIO_TO_FLOW에 한 줄 추가
        4. manifest.py의 flows.handlers에 handler 등록

    인터럽트(mid-flow 시나리오 전환):
        이체 진행 중 다른 시나리오 요청 → 요청된 flow로 안내.
        이체 state는 보존되므로 다음 TRANSFER 요청 시 이어서 진행 가능.
        ctx.metadata["prior_scenario"]에 이전 시나리오명이 담겨있음.
    """

    SCENARIO_TO_FLOW: dict = {
        "TRANSFER": "TRANSFER_FLOW",
        "GENERAL":  "DEFAULT_FLOW",
        # "BALANCE_CHECK": "BALANCE_FLOW",   ← 새 서비스 한 줄 추가
        # "CARD_APPLY":    "CARD_FLOW",
    }

    def route(self, *, intent_result: dict, state: TransferState) -> str:
        scenario = intent_result.get("scenario", "GENERAL")
        return self.SCENARIO_TO_FLOW.get(scenario, "DEFAULT_FLOW")
