# app/core/tracing.py
"""
TurnTracer: 턴 단위 에이전트 실행 추적기.

AgentRunner가 매 에이전트 실행마다 자동으로 record()를 호출한다.
Orchestrator가 턴 시작 시 생성하고, DONE payload에 summary()를 삽입한다.

사용 흐름:
    tracer = TurnTracer(session_id)
    ctx = ExecutionContext(..., tracer=tracer)
    # AgentRunner가 자동으로 tracer.record() 호출
    final_payload["_trace"] = tracer.summary()
"""

import time
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class AgentRecord:
    """단일 에이전트 실행 기록."""

    agent: str
    elapsed_ms: float
    success: bool
    retries: int = 0
    error: str | None = None


class TurnTracer:
    """턴 시작 시 생성. AgentRunner가 자동으로 record() 호출."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turn_id = uuid4().hex[:8]
        self._started = time.monotonic()
        self._records: list[AgentRecord] = []

    def record(self, rec: AgentRecord) -> None:
        self._records.append(rec)

    @property
    def records(self) -> list[AgentRecord]:
        return list(self._records)

    @property
    def last(self) -> AgentRecord | None:
        return self._records[-1] if self._records else None

    def summary(self) -> dict:
        """DONE payload의 _trace 필드에 삽입할 요약."""
        return {
            "turn_id": self.turn_id,
            "total_elapsed_ms": round((time.monotonic() - self._started) * 1000, 1),
            "agents": [
                {
                    "agent": r.agent,
                    "elapsed_ms": r.elapsed_ms,
                    "success": r.success,
                    "retries": r.retries,
                    "error": r.error,
                }
                for r in self._records
            ],
        }
