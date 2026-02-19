# app/core/events.py
"""
SSE 스트림을 통해 프론트엔드로 전달되는 이벤트 타입 상수.

이벤트는 항상 {"event": EventType, "payload": dict} 형태로 yield된다.
프론트엔드는 event 타입으로 분기해 각 payload를 처리한다.

────────────────────────────────────────────────────────
  한 턴의 이벤트 흐름 예시 (InteractionAgent 스트리밍):

  AGENT_START  {"agent": "intent",       "label": "의도 파악 중"}
  AGENT_DONE   {"agent": "intent",       "success": True, "result": "TRANSFER"}
  AGENT_START  {"agent": "slot",         "label": "정보 추출 중"}
  AGENT_DONE   {"agent": "slot",         "success": True}
  AGENT_START  {"agent": "interaction",  "label": "응답 생성 중"}
  LLM_TOKEN    "안"
  LLM_TOKEN    "녕"          ← 글자 단위 스트리밍
  LLM_DONE     {"action": "ASK", "message": "안녕하세요..."}
  AGENT_DONE   {"agent": "interaction",  "success": True}
  DONE         {"message": "...", "next_action": "ASK", "state_snapshot": {...}}
────────────────────────────────────────────────────────
"""

from enum import Enum


class EventType(str, Enum):
    # ── 턴 종료 ──────────────────────────────────────────────────────────────
    DONE = "DONE"
    """
    한 턴의 최종 응답. FlowHandler가 마지막으로 yield한다.

    payload 필드:
      message        str   사용자에게 표시할 최종 메시지
      next_action    str   UI 힌트 ("ASK" | "CONFIRM" | "DONE" | "ASK_CONTINUE")
      ui_hint        dict  버튼 목록 등 UI 정책 {"buttons": ["확인", "취소"]}
      state_snapshot dict  state.model_dump() — 프론트 상태 표시용
      hooks          list  프론트로 전달할 훅 이벤트 [{"type": "...", "data": {...}}]
    """

    # ── LLM 스트리밍 ─────────────────────────────────────────────────────────
    LLM_TOKEN = "LLM_TOKEN"
    """
    LLM이 반환하는 토큰 단위 스트림.
    ConversationalAgent는 JSON 전체를 버퍼에 모은 뒤 message 필드를 글자 단위로 emit.

    payload: str  (단일 토큰 또는 글자)
    """

    LLM_DONE = "LLM_DONE"
    """
    LLM 응답 완료. 파싱된 전체 payload를 포함한다.
    FlowHandler._stream_agent_turn()이 이 이벤트의 payload를 DONE 이벤트에 전달한다.

    payload 필드 (에이전트마다 다름):
      action   str   에이전트가 결정한 다음 동작
      message  str   사용자에게 보낼 메시지
      (+ 에이전트별 추가 필드)
    """

    # ── 에이전트 생명주기 ─────────────────────────────────────────────────────
    AGENT_START = "AGENT_START"
    """
    에이전트 실행 시작. 프론트는 이 이벤트로 로딩 UI를 표시한다.
    재시도 시 같은 agent 이름으로 다시 emit되어 라벨이 업데이트된다.

    payload 필드:
      agent  str  에이전트 키 ("intent" | "slot" | "interaction" | "execute" | ...)
      label  str  사용자 친화적 설명 ("의도 파악 중", "정보 추출 중", ...)
    """

    AGENT_DONE = "AGENT_DONE"
    """
    에이전트 실행 완료(성공 또는 실패).

    payload 필드:
      agent        str   에이전트 키
      label        str   완료 설명
      success      bool  True=성공, False=실패
      retry_count  int   재시도 횟수 (0이면 첫 시도에 성공)
      result       str   (선택) 분류 결과 요약 (intent 에이전트에서 시나리오명 등)
    """

    # ── 배치 처리 ────────────────────────────────────────────────────────────
    TASK_PROGRESS = "TASK_PROGRESS"
    """
    배치(다건) 처리 시 현재 진행 상황. 프론트는 프로그레스 바를 업데이트한다.

    payload 필드:
      index  int   현재 처리 중인 작업 번호 (1-based)
      total  int   전체 작업 수
      slots  dict  현재 작업의 slot 정보 {"target": "홍길동", "amount": 50000}
    """
