# app/core/memory/memory_manager.py
"""
대화 메모리 관리 — 표준 Context Engineering 패턴.

┌─────────────────────────────────────────────────────────┐
│  Context Window 구성                                     │
│                                                         │
│  [System Prompt]                                        │
│  [Memory Block]  ← summary_text (압축된 장기 기억)       │
│  [Recent Turns]  ← raw_history (최근 N턴, 원본)          │
│  [Current Turn]  ← user_message                        │
└─────────────────────────────────────────────────────────┘

자동 요약 흐름:
  raw_history 턴 수 ≥ summarize_threshold
      ↓
  오래된 턴 (keep_recent 이전) → LLM 요약 → summary_text 갱신
      ↓
  raw_history = 최근 keep_recent 턴만 유지

summary_text는 세션 리셋(이체 완료/취소) 후에도 유지 → 사용자 장기 맥락 보존.
"""

from app.core.config import settings
from app.core.logging import setup_logger

# ── 기본 요약 프롬프트 ─────────────────────────────────────────────────────────
# 서비스별 manifest에서 override 가능
_DEFAULT_SUMMARY_SYSTEM = (
    "You are a concise conversation summarizer. "
    "Preserve all factual details. Omit pleasantries and repetitions."
)

_DEFAULT_SUMMARY_TEMPLATE = (
    "Summarize the conversation below into 3-5 sentences.\n"
    "Preserve: names, amounts, dates, decisions made, and key context.\n"
    "Drop: greetings, filler, repeated exchanges.\n\n"
    "{memory_block}"
    "Additional dialogue:\n"
    "{dialog}\n\n"
    "Summary:"
)

_MEMORY_BLOCK_TEMPLATE = (
    "Previous summary:\n"
    "{summary}\n\n"
)


class MemoryManager:
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
        self.enable_memory = enable_memory
        self.enable_summary = (
            enable_summary if enable_summary is not None else settings.MEMORY_ENABLE_SUMMARY
        )
        self.summarize_threshold = summarize_threshold or settings.MEMORY_SUMMARIZE_THRESHOLD
        self.keep_recent_turns = keep_recent_turns or settings.MEMORY_KEEP_RECENT_TURNS
        self.summary_model = summary_model or settings.MEMORY_SUMMARY_MODEL
        self.summary_system_prompt = summary_system_prompt or _DEFAULT_SUMMARY_SYSTEM
        self.summary_user_template = summary_user_template or _DEFAULT_SUMMARY_TEMPLATE
        self.logger = setup_logger("MemoryManager")
        self._llm = None  # lazy init

    @property
    def llm(self):
        if self._llm is None:
            from app.core.llm.openai_client import OpenAIClient
            self._llm = OpenAIClient()
        return self._llm

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(self, memory: dict, user_msg: str, assistant_msg: str) -> None:
        """턴 추가 후 필요 시 자동 요약."""
        if not self.enable_memory:
            return

        history = memory.setdefault("raw_history", [])
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})

        if self.enable_summary and len(history) // 2 >= self.summarize_threshold:
            self._summarize(memory)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _summarize(self, memory: dict) -> None:
        """오래된 턴 → LLM 요약 → summary_text 갱신, raw_history 압축."""
        history = memory["raw_history"]
        keep_msgs = self.keep_recent_turns * 2  # (user, assistant) 쌍 기준

        to_compress = history[:-keep_msgs]
        if not to_compress:
            return

        try:
            new_summary = self._call_llm(to_compress, memory.get("summary_text", ""))
            memory["summary_text"] = new_summary
            memory["raw_history"] = history[-keep_msgs:]
            self.logger.info(
                f"[MemoryManager] summarized {len(to_compress) // 2} turns → "
                f"raw_history {len(memory['raw_history']) // 2} turns retained"
            )
        except Exception as e:
            # 요약 실패 시 단순 trim으로 fallback (summary 건드리지 않음)
            self.logger.warning(f"[MemoryManager] summarization failed, fallback trim: {e}")
            memory["raw_history"] = history[-(settings.MEMORY_MAX_RAW_TURNS * 2):]

    def _call_llm(self, messages: list, prev_summary: str) -> str:
        """표준 context engineering 형식으로 LLM 요약 요청."""
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
            temperature=0,
            messages=[
                {"role": "system", "content": self.summary_system_prompt},
                {"role": "user",   "content": user_content},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
