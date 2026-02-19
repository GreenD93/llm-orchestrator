# app/core/agents/agent_result.py
"""
AgentResult: 에이전트가 성공/실패/정보부족을 표현하는 표준 응답.

기존 에이전트는 dict를 반환하므로 변경 없이 동작한다.
새 에이전트에서 AgentResult를 반환하면 AgentRunner가 to_dict()로 자동 변환한다.

사용 예시:
    # 성공
    return AgentResult.success({"action": "ASK", "message": "안녕하세요"})

    # 파라미터 부족
    return AgentResult.need_info(["amount"], "이체 금액을 알려주세요.")

    # 처리 불가
    return AgentResult.cannot_handle("해외 이체는 지원하지 않습니다.")

    # 부분 성공 (파싱 에러 등)
    return AgentResult.partial({"operations": []}, reason="parse_error")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResultStatus(str, Enum):
    SUCCESS = "success"
    NEED_INFO = "need_info"
    CANNOT_HANDLE = "cannot_handle"
    PARTIAL = "partial"


@dataclass
class AgentResult:
    """에이전트 표준 응답. AgentRunner가 to_dict()로 변환해 FlowHandler에 전달한다."""

    status: ResultStatus
    data: dict = field(default_factory=dict)
    missing: list[str] | None = None
    reason: str | None = None
    message: str | None = None

    @classmethod
    def success(cls, data: dict) -> AgentResult:
        return cls(status=ResultStatus.SUCCESS, data=data)

    @classmethod
    def need_info(cls, missing: list[str], message: str, data: dict | None = None) -> AgentResult:
        return cls(status=ResultStatus.NEED_INFO, data=data or {}, missing=missing, message=message)

    @classmethod
    def cannot_handle(cls, reason: str, data: dict | None = None) -> AgentResult:
        return cls(status=ResultStatus.CANNOT_HANDLE, data=data or {}, reason=reason)

    @classmethod
    def partial(cls, data: dict, reason: str | None = None, message: str | None = None) -> AgentResult:
        return cls(status=ResultStatus.PARTIAL, data=data, reason=reason, message=message)

    def to_dict(self) -> dict:
        """AgentRunner가 FlowHandler에 전달하기 전 dict으로 변환."""
        result = dict(self.data)
        result["_result_status"] = self.status.value
        if self.missing:
            result["_missing"] = self.missing
        if self.reason:
            result["_reason"] = self.reason
        if self.message and "message" not in result:
            result["message"] = self.message
        return result
