# app/projects/transfer/agents/transfer_execute_agent/agent.py
"""실제 이체 실행. RetryableError / FatalExecutionError만 raise."""

from app.core.agents.base_agent import BaseAgent
from app.core.agents import RetryableError, FatalExecutionError
from app.projects.transfer.state.models import TransferState
from app.projects.transfer.agents.transfer_execute_agent.prompt import get_system_prompt


class TransferExecuteAgent(BaseAgent):
    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, state: TransferState, **kwargs) -> dict:
        try:
            _ = state.slots.target
            _ = state.slots.amount
            return {"success": True, "transaction_id": "mock-tx-001"}
        except Exception as e:
            if "timeout" in str(e).lower() or "unavailable" in str(e).lower():
                raise RetryableError(str(e))
            raise FatalExecutionError(str(e))
