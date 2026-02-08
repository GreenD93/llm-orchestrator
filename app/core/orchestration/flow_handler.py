# app/core/orchestration/flow_handler.py
"""FlowHandler: agent 실행만. run(ctx)에서 Runner로 에이전트 호출·이벤트 yield. flow 결정은 Router 담당."""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext


class BaseFlowHandler:
    """
    executors 대신 runner 한 개. get(agent_name)으로 Runner.run(agent_name, ctx) 호출.
    업무 순서만 정의하고, 세션/메모리 저장은 필요 시 flow_utils.update_memory_and_save 사용.
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

    def get(self, agent_name: str):
        """Runner를 반환해 호출부에서 runner.run(agent_name, ctx) 사용."""
        return self.runner

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        raise NotImplementedError
