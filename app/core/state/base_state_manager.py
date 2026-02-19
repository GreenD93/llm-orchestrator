# app/core/state/base_state_manager.py
"""
State 전이 로직의 인터페이스.

FlowHandler는 LLM(SlotFillerAgent 등)의 출력(delta)을 받아
StateManager.apply(delta)를 호출한다. 실제 전이 로직은 프로젝트별로 구현한다.

─── delta 형식 ─────────────────────────────────────────────────────────────
delta는 LLM이 반환한 조작 명령 목록. 서비스마다 다를 수 있다.

transfer 서비스 예시:
  {"operations": [
      {"op": "set",   "slot": "target", "value": "홍길동"},
      {"op": "set",   "slot": "amount", "value": 50000},
      {"op": "confirm"},          ← READY → CONFIRMED 전환 요청
      {"op": "cancel_flow"},      ← 취소 처리
      {"op": "continue_flow"},    ← 이어서 진행
  ]}

단순 서비스 예시 (상태 머신 없음):
  {}   ← MinimalStateManager처럼 delta를 무시하고 state를 그대로 반환해도 됨

─── 구현 방법 ──────────────────────────────────────────────────────────────
    class MyStateManager(BaseStateManager):
        def __init__(self, state: MyState):
            super().__init__(state)
            self.state: MyState = state

        def apply(self, delta: dict) -> MyState:
            for op in delta.get("operations", []):
                self._apply_op(op)
            self._validate()
            self._transition()
            return self.state
"""

from typing import Any, Dict


class BaseStateManager:
    """프로젝트별 State 전이 로직. Core는 인터페이스만 정의한다."""

    def __init__(self, state: Any):
        self.state = state

    def apply(self, delta: Dict[str, Any]) -> Any:
        """
        LLM delta를 state에 반영한 뒤 갱신된 state를 반환한다.

        Args:
            delta: LLM이 반환한 조작 명령. 형식은 서비스마다 다르다 (위 docstring 참고).

        Returns:
            갱신된 state 객체 (self.state와 동일한 인스턴스).
        """
        raise NotImplementedError
