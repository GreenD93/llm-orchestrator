# app/projects/transfer/agents/transfer_execute_agent/agent.py
"""
TransferExecuteAgent: 이체 실행 에이전트.

실제 은행 API·결제 시스템 연동 지점.
현재 구현은 Mock — 실서비스 연동 시 run() 내부의 mock 코드를 교체한다.

─── 오류 분류 ────────────────────────────────────────────────────────────────
  RetryableError:     네트워크 타임아웃, 서비스 일시 장애 등 재시도 가능한 오류.
                      AgentRunner가 max_retry 횟수만큼 자동 재시도한다.
  FatalExecutionError: 잘못된 계좌, 한도 초과 등 재시도해도 해결 안 되는 오류.
                      즉시 실패 처리 (FAILED 단계로 전이).

─── 연동 교체 방법 ───────────────────────────────────────────────────────────
  1. run() 내부의 mock 코드를 실제 API 호출로 교체
  2. 타임아웃/네트워크 오류 → RetryableError raise
  3. 비즈니스 오류(한도 초과, 계좌 없음 등) → FatalExecutionError raise
  4. 성공 시 {"success": True, "transaction_id": "실제 트랜잭션 ID"} 반환
"""

from app.core.agents.base_agent import BaseAgent
from app.core.agents.agent_runner import RetryableError, FatalExecutionError
from app.core.context import ExecutionContext
from app.projects.transfer.agents.transfer_execute_agent.prompt import get_system_prompt


class TransferExecuteAgent(BaseAgent):
    """
    이체를 실제 실행하는 에이전트.

    LLM을 호출하지 않는다 (system_prompt는 미래 확장 또는 실패 메시지 생성용).
    state.slots에서 target·amount를 읽어 API를 호출한다.
    """

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        """
        이체를 실행하고 결과를 반환한다.

        Returns:
            {"success": True, "transaction_id": "..."}

        Raises:
            RetryableError:      재시도 가능한 오류 (타임아웃, 서비스 일시 장애)
            FatalExecutionError: 재시도 불가 오류 (계좌 오류, 한도 초과 등)
        """
        state = context.state
        try:
            # ── TODO: 실제 은행 API 연동으로 교체 ──────────────────────────
            # 현재는 slots 접근 성공 여부만 확인하는 Mock 구현
            _ = state.slots.target
            _ = state.slots.amount
            return {"success": True, "transaction_id": "mock-tx-001"}
            # ────────────────────────────────────────────────────────────────
        except Exception as e:
            if "timeout" in str(e).lower() or "unavailable" in str(e).lower():
                raise RetryableError(str(e))
            raise FatalExecutionError(str(e))
