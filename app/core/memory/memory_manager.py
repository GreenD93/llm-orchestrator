# app/core/memory/memory_manager.py
"""
대화 메모리 관리 — 표준 Context Engineering 패턴.

─── Context Window 구성 ──────────────────────────────────────────────────────
  ┌─────────────────────────────────────────────────────────┐
  │  [System Prompt]         ← BaseAgent.system_prompt      │
  │  [Memory Block]          ← summary_text (압축 장기 기억) │
  │  [Recent Turns]          ← raw_history (최근 N턴 원본)   │
  │  [Current Turn]          ← user_message                 │
  └─────────────────────────────────────────────────────────┘

  ExecutionContext.build_messages()가 이 구조로 LLM 메시지를 조합한다.

─── 자동 요약 흐름 ──────────────────────────────────────────────────────────
  raw_history 턴 수 ≥ summarize_threshold (기본 6)
      ↓
  오래된 턴 (keep_recent 이전 부분) → LLM 요약 → summary_text 갱신
      ↓
  raw_history = 최근 keep_recent 턴만 유지

  summary_text는 이체 완료·취소 후 세션 리셋 시에도 유지된다.
  사용자의 장기 맥락(선호하는 수신인, 금액 패턴 등)이 보존된다.

─── 설정 (config.py) ────────────────────────────────────────────────────────
  MEMORY_SUMMARIZE_THRESHOLD: 요약 트리거 턴 수 (기본 6)
  MEMORY_KEEP_RECENT_TURNS:   요약 후 유지할 턴 수 (기본 3)
  MEMORY_SUMMARY_MODEL:       요약 LLM 모델 (기본 "gpt-4o-mini")
  MEMORY_ENABLE_SUMMARY:      요약 활성화 여부 (기본 True)
  MEMORY_MAX_RAW_TURNS:       요약 실패 시 trim 상한 (기본 10)
"""

from app.core.config import settings
from app.core.logging import setup_logger

# ── 기본 요약 프롬프트 ─────────────────────────────────────────────────────────
# manifest.py에서 MemoryManager(summary_system_prompt=..., summary_user_template=...)로 override 가능

_DEFAULT_SUMMARY_SYSTEM = (
    "You are a concise conversation summarizer. "
    "Preserve all factual details. Omit pleasantries and repetitions."
)

_DEFAULT_SUMMARY_TEMPLATE = (
    "Summarize the conversation below into 3-5 sentences.\n"
    "Preserve: names, amounts, dates, decisions made, and key context.\n"
    "Drop: greetings, filler, repeated exchanges.\n\n"
    "{memory_block}"           # 이전 요약이 있으면 "Previous summary:\n...\n\n"
    "Additional dialogue:\n"
    "{dialog}\n\n"             # "User: ...\nAssistant: ..." 형식
    "Summary:"
)

_MEMORY_BLOCK_TEMPLATE = (
    "Previous summary:\n"
    "{summary}\n\n"
)


class MemoryManager:
    """
    대화 메모리를 관리하는 클래스.

    manifest.py에서 인스턴스를 생성해 CoreOrchestrator에 주입한다.

    사용 예시 (manifest.py):
        "memory_manager_factory": lambda: MemoryManager(
            enable_memory=True,
            summarize_threshold=6,
            keep_recent_turns=3,
            summary_model="gpt-4o-mini",
        )
    """

    def __init__(
        self,
        enable_memory: bool = True,
        enable_summary: bool | None = None,
        summarize_threshold: int | None = None,
        keep_recent_turns: int | None = None,
        summary_model: str | None = None,
        # 서비스별 override 포인트 — None이면 모듈 상단 기본값 사용
        summary_system_prompt: str | None = None,
        summary_user_template: str | None = None,
    ):
        """
        Args:
            enable_memory:         False면 메모리 갱신을 완전히 건너뜀
            enable_summary:        None이면 settings.MEMORY_ENABLE_SUMMARY 사용
            summarize_threshold:   요약 트리거 기준 턴 수. None이면 settings 값 사용
            keep_recent_turns:     요약 후 유지할 최근 턴 수
            summary_model:         요약 LLM 모델명
            summary_system_prompt: 요약 LLM system 메시지 override
            summary_user_template: 요약 LLM user 메시지 템플릿 override ({memory_block}, {dialog} 변수 필요)
        """
        self.enable_memory = enable_memory
        self.enable_summary = (
            enable_summary if enable_summary is not None else settings.MEMORY_ENABLE_SUMMARY
        )
        self.summarize_threshold = summarize_threshold or settings.MEMORY_SUMMARIZE_THRESHOLD
        self.keep_recent_turns   = keep_recent_turns   or settings.MEMORY_KEEP_RECENT_TURNS
        self.summary_model       = summary_model       or settings.MEMORY_SUMMARY_MODEL
        self.summary_system_prompt  = summary_system_prompt  or _DEFAULT_SUMMARY_SYSTEM
        self.summary_user_template  = summary_user_template  or _DEFAULT_SUMMARY_TEMPLATE
        self.logger = setup_logger("MemoryManager")
        self._llm = None   # lazy init — LLM은 요약이 필요할 때만 초기화

    @property
    def llm(self):
        """LLM 클라이언트를 지연 초기화. 요약이 필요없으면 OpenAI 클라이언트를 생성하지 않는다."""
        if self._llm is None:
            from app.core.llm.openai_client import OpenAIClient
            self._llm = OpenAIClient()
        return self._llm

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(self, memory: dict, user_msg: str, assistant_msg: str) -> None:
        """
        대화 한 턴을 memory에 추가하고, 필요 시 자동 요약을 실행한다.

        Args:
            memory:         sessions.get_or_create()가 반환한 memory dict (in-place 수정됨)
            user_msg:       사용자 발화 원문
            assistant_msg:  LLM 응답 텍스트 (payload["message"])

        Notes:
            memory dict는 참조로 전달되므로 갱신이 세션에 즉시 반영된다.
            sessions.save_state()는 별도로 flow_utils.update_memory_and_save()에서 호출한다.
        """
        if not self.enable_memory:
            return

        history = memory.setdefault("raw_history", [])
        history.append({"role": "user",      "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})

        # 턴 수(= 메시지 수 // 2) 가 threshold에 도달하면 자동 요약
        if self.enable_summary and len(history) // 2 >= self.summarize_threshold:
            self._summarize(memory)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _summarize(self, memory: dict) -> None:
        """
        오래된 턴을 LLM으로 요약하고 raw_history를 압축한다.

        처리:
          - 앞부분 (to_compress): 요약 대상 — keep_recent_turns 이전 메시지들
          - 뒷부분 (keep_msgs):   유지 대상 — 최근 keep_recent_turns 턴
        """
        history  = memory["raw_history"]
        keep_msgs = self.keep_recent_turns * 2  # 1턴 = user + assistant 2개 메시지

        to_compress = history[:-keep_msgs]
        if not to_compress:
            return   # keep_recent_turns 이전에 압축할 내용 없음

        try:
            new_summary = self._call_llm(to_compress, memory.get("summary_text", ""))
            memory["summary_text"] = new_summary
            memory["raw_history"]  = history[-keep_msgs:]
            self.logger.info(
                f"[MemoryManager] summarized {len(to_compress) // 2} turns → "
                f"raw_history {len(memory['raw_history']) // 2} turns retained"
            )
        except Exception as e:
            # 요약 실패 시 summary는 건드리지 않고 단순 trim으로 fallback
            self.logger.warning(f"[MemoryManager] summarization failed, fallback trim: {e}")
            memory["raw_history"] = history[-(settings.MEMORY_MAX_RAW_TURNS * 2):]

    def _call_llm(self, messages: list, prev_summary: str) -> str:
        """
        LLM에 요약을 요청하고 결과 텍스트를 반환한다.

        Context Engineering 구조:
          - system: "간결한 요약자"
          - user:   (이전 요약 있으면 포함) + 압축 대상 대화 → "Summary:"
        """
        dialog = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages
        )
        memory_block = (
            _MEMORY_BLOCK_TEMPLATE.format(summary=prev_summary)
            if prev_summary else ""
        )
        user_content = self.summary_user_template.format(
            memory_block=memory_block,
            dialog=dialog,
        )
        resp = self.llm.chat(
            model=self.summary_model,
            temperature=0,   # 요약은 결정론적으로
            messages=[
                {"role": "system", "content": self.summary_system_prompt},
                {"role": "user",   "content": user_content},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
