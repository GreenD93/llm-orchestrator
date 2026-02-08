"""단일 flow만 있으므로 항상 DEFAULT_FLOW 반환."""

from app.core.orchestration import BaseFlowRouter


class MinimalFlowRouter(BaseFlowRouter):
    def route(self, *, intent: str, state) -> str:
        return "DEFAULT_FLOW"
