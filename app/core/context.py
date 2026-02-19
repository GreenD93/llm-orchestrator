# app/core/context.py
"""
ExecutionContext: 단일 턴 실행에 필요한 모든 데이터를 담는 컨테이너.

─── 설계 원칙 ────────────────────────────────────────────────────────────────
  - 비즈니스 로직 없음. 데이터 컨테이너 역할만 한다.
  - Agent는 ExecutionContext를 통해서만 세션 상태에 접근한다.
  - Orchestrator가 생성하고, FlowHandler → Agent 순으로 참조한다.
  - state는 FlowHandler가 StateManager를 통해 수정한다. Agent는 읽기만 한다.

─── 데이터 흐름 ─────────────────────────────────────────────────────────────
  Orchestrator
      ↓ sessions.get_or_create(session_id)
      ↓ ExecutionContext(session_id, user_message, state, memory, metadata)
  FlowHandler
      ↓ handler.run(ctx)
      ↓ ctx.state = state_manager.apply(delta)   ← 상태 수정
  Agent
      ↓ context.build_messages()                  ← 읽기 전용
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ExecutionContext:
    """
    단일 턴 실행 컨텍스트. Orchestrator가 생성해 FlowHandler와 Agent에 전달한다.

    Attributes:
        session_id:   사용자 세션 고유 식별자
        user_message: 현재 턴의 사용자 발화 원문
        state:        프로젝트 State 객체 (BaseState 상속). FlowHandler가 수정 가능.
        memory:       대화 메모리 dict.
                      "raw_history": [{"role": "user"|"assistant", "content": "..."}]
                      "summary_text": "이전 대화 요약 텍스트"
        metadata:     턴 내 임시 데이터 전달용 dict.
                      "execution":     AgentRunner가 기록하는 에러 정보
                      "prior_scenario": 시나리오 전환 감지 시 이전 시나리오 이름
                      기타 FlowHandler 간 데이터 공유에 자유롭게 사용 가능.
    """

    session_id:   str
    user_message: str
    state:        Any             # 프로젝트 State (BaseState 상속)
    memory:       Dict[str, Any]  # raw_history, summary_text 등
    metadata:     Dict[str, Any] = field(default_factory=dict)
    tracer:       Any = None      # TurnTracer | None — 에이전트 실행 추적기

    def get_history(self, last_n: int = 12) -> list:
        """
        raw_history에서 최근 last_n 개 메시지를 반환한다.

        Args:
            last_n: 반환할 메시지 수 (user + assistant 각각 1개씩 카운트).
                    예: last_n=4 → 최근 2턴 (user 2개 + assistant 2개)

        Returns:
            [{"role": "user"|"assistant", "content": "..."}, ...]
        """
        return self.memory.get("raw_history", [])[-last_n:]

    def build_messages(self, context_block: str = "", last_n_turns: int = 6) -> list:
        """
        표준 Context Engineering 메시지 빌더.

        반환 구조:
          1. [system]     context_block + (이전 대화 요약)   ← 에이전트별 동적 컨텍스트
          2. [user/asst]  최근 last_n_turns 턴 대화 히스토리
          3. [user]       현재 사용자 메시지

        모든 Agent에서 이 메서드를 사용하면 메모리 패턴이 일관된다.
        BaseAgent.chat()이 system_prompt를 앞에 별도로 prepend하므로
        context_block에는 정적 지침이 아닌 동적 상태 정보만 담는다.

        Args:
            context_block: 에이전트별 동적 컨텍스트.
                           예: "오늘 날짜: 2026-02-19\n현재 이체 상태: {...}"
            last_n_turns:  포함할 최근 대화 턴 수 (1턴 = user + assistant 쌍)

        Returns:
            [{"role": ..., "content": ...}, ...] 형식의 메시지 목록.
            BaseAgent.chat()이 system_prompt를 prepend한 뒤 LLM에 전달한다.
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
