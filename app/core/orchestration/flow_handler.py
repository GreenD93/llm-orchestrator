# app/core/orchestration/flow_handler.py
"""FlowHandler: agent 실행만. run(ctx)에서 Runner로 에이전트 호출·이벤트 yield. flow 결정은 Router 담당."""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext


class BaseFlowHandler:
    """
    runner 한 개로 Agent 실행. 업무 순서만 정의.
    메모리 갱신은 flow_utils.update_memory 사용, 상태 저장은 Orchestrator finally에서 수행.
    """

    def __init__(
        self,
        runner: Any,  # AgentRunner
        sessions: Any,
        memory_manager: Any,
        state_manager_factory: Any,
        completed: Any = None,
    ):
        self.runner = runner
        self.sessions = sessions
        self.memory_manager = memory_manager
        self.state_manager_factory = state_manager_factory
        self.completed = completed

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        raise NotImplementedError
