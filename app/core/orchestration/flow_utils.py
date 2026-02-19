# app/core/orchestration/flow_utils.py
"""
FlowHandler 공통 유틸리티.

BaseFlowHandler._stream_agent_turn() 내부에서 호출된다.
직접 사용할 일은 드물며, 커스텀 FlowHandler에서 필요 시 임포트한다.
"""

from typing import Any


def update_memory_and_save(
    memory_manager: Any,
    sessions: Any,
    session_id: str,
    state: Any,
    memory: dict,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    대화 메모리 갱신 후 세션 저장.

    호출 시점: FlowHandler._stream_agent_turn() — 마지막 에이전트 응답 수신 직후.

    처리 순서:
      1. memory_manager.update()  — raw_history 추가, 필요 시 자동 요약
      2. sessions.save_state()    — 갱신된 state + memory 영속화

    Args:
        memory_manager:   MemoryManager 인스턴스
        sessions:         SessionStore 인스턴스
        session_id:       현재 세션 ID
        state:            현재 State 객체 (BaseState 상속)
        memory:           현재 메모리 dict (raw_history, summary_text 등)
        user_message:     사용자 발화 원문
        assistant_message: LLM이 반환한 응답 텍스트 (payload["message"])
    """
    memory_manager.update(memory, user_message, assistant_message)
    sessions.save_state(session_id, state)
