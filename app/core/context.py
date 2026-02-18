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

    def get_history(self, last_n: int = 12) -> list:
        """memory["raw_history"]에서 최근 last_n 개 메시지 반환 (user+assistant 쌍 단위)."""
        return self.memory.get("raw_history", [])[-last_n:]

    def build_messages(self, context_block: str = "", last_n_turns: int = 6) -> list:
        """
        표준 Context Engineering 메시지 빌더.

        구조:
          [system: context_block (+ 이전 대화 요약)]  ← 동적 컨텍스트
          [최근 대화 히스토리]                          ← raw_history 최근 N턴
          [현재 사용자 메시지]                          ← user_message

        모든 Agent에서 이 메서드를 사용하면 메모리 패턴이 일관된다.

        Args:
            context_block: 에이전트별 동적 컨텍스트 (state 정보, stage 등).
                           BaseAgent.chat()이 system_prompt를 앞에 별도로 붙이므로
                           여기에는 정적 지침이 아닌 동적 상태만 담는다.
            last_n_turns: 포함할 최근 대화 턴 수 (1턴 = user + assistant 메시지 쌍)
        """
        summary = self.memory.get("summary_text", "")
        parts = []
        if context_block:
            parts.append(context_block)
        if summary:
            parts.append(f"## 이전 대화 요약\n{summary}")

        # 1턴 = user + assistant 2개 메시지
        history = self.get_history(last_n_turns * 2)
        msgs = []
        if parts:
            msgs.append({"role": "system", "content": "\n\n".join(parts)})
        msgs.extend(history)
        msgs.append({"role": "user", "content": self.user_message})
        return msgs
