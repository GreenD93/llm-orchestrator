# app/core/context.py
"""실행 컨텍스트: state, memory, metadata를 하나로 묶은 데이터 컨테이너. 비즈니스 로직 없음."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ExecutionContext:
    """
    단일 턴 실행에 필요한 데이터만 보관.
    Agent는 Context를 통해서만 상태에 접근한다.
    """
    session_id: str
    user_message: str
    state: Any  # 프로젝트 State (BaseState 상속)
    memory: Dict[str, Any]  # raw_history, summary_text 등
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_history(self, last_n: int = 6) -> list:
        """memory["raw_history"]에서 최근 last_n 턴 반환."""
        return self.memory.get("raw_history", [])[-last_n:]
