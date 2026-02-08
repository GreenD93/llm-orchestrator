# app/core/orchestration/flow_handler.py
"""FlowHandler: 업무 순서 정의만. executors 접근, run() 추상, get(agent_name). 공통 로직은 flow_utils 사용."""

from typing import Any, Dict, Generator


class BaseFlowHandler:
    """
    - executors 접근, get(agent_name), run() 추상 메서드만 보유.
    - history/저장 등 공통 로직은 flow_utils.get_history, flow_utils.update_and_save 사용.
    """

    def __init__(
        self,
        executors: Dict[str, Any],
        memory: Any,
        sessions: Any,
        state_manager_factory: Any,
        completed: Any = None,
    ):
        self.executors = executors
        self.memory = memory
        self.sessions = sessions
        self.state_manager_factory = state_manager_factory
        self.completed = completed  # optional: 완료 이력 저장 시에만 사용

    def get(self, agent_name: str):
        return self.executors[agent_name]

    def run(self, **kwargs) -> Generator[Dict[str, Any], None, None]:
        raise NotImplementedError
