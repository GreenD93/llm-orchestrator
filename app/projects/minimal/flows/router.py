# app/projects/minimal/flows/router.py
from app.core.orchestration import BaseFlowRouter


class MinimalFlowRouter(BaseFlowRouter):
    """모든 요청을 DEFAULT_FLOW로 라우팅. IntentAgent 없음."""

    def route(self, *, intent_result: dict, state) -> str:
        return "DEFAULT_FLOW"
