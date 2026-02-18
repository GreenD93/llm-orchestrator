# frontend/app.py
"""AI 이체 서비스 - Streamlit 채팅 프론트엔드"""

import sys
import os
import uuid

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from api_client import stream_chat, get_completed, get_debug

# ─── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 이체 서비스",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── 에이전트 로그 아이템 ─────────────────────────────────────────── */
.agent-item {
    padding: 7px 12px; margin: 3px 0;
    border-radius: 6px; font-size: 13px; line-height: 1.4;
}
/* rgba 배경 → 라이트/다크 모두 대응 */
.agent-running { background: rgba(255,179,0,0.12); border-left: 3px solid #FFB300; }
.agent-done    { background: rgba(67,160,71,0.12);  border-left: 3px solid #43A047; }
.agent-error   { background: rgba(229,57,53,0.12);  border-left: 3px solid #E53935; }
.agent-result  { opacity: 0.65; margin-left: 6px; }

/* ── 스테이지 뱃지 ───────────────────────────────────────────────── */
.stage-badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 12px; font-weight: 600; color: white; margin-bottom: 8px;
}

/* ── 슬롯 정보 행 ────────────────────────────────────────────────── */
.slot-row {
    display: flex; justify-content: space-between;
    padding: 5px 0; border-bottom: 1px solid rgba(128,128,128,0.2);
    font-size: 13px;
}
.slot-label { opacity: 0.55; }
.slot-value { font-weight: 500; }
.slot-empty { opacity: 0.35; }

/* ── 완료 거래 카드 ──────────────────────────────────────────────── */
.tx-card {
    background: rgba(128,128,128,0.08);
    border-radius: 8px; padding: 10px 14px;
    margin: 6px 0; border-left: 3px solid #4CAF50; font-size: 13px;
}
.tx-failed    { border-left-color: #E53935 !important; }
.tx-cancelled { border-left-color: #9E9E9E !important; }
.tx-detail    { opacity: 0.65; font-size: 12px; }
.tx-memo      { opacity: 0.55; font-size: 12px; }

/* ── 배치 큐 ─────────────────────────────────────────────────────── */
.batch-queue-header {
    font-size: 11px; opacity: 0.5; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin: 8px 0 4px 0;
}
.batch-item {
    padding: 4px 8px; margin: 2px 0;
    border-radius: 4px; font-size: 13px;
}
.batch-pending  { opacity: 0.45; }
.batch-exec     { color: #2196F3; font-weight: 600; background: rgba(33,150,243,0.12); }
.batch-done     { color: #4CAF50; }
.batch-failed   { color: #F44336; }

/* ── 안내 텍스트 (muted) ─────────────────────────────────────────── */
.muted { opacity: 0.5; font-size: 13px; margin: 0; }
</style>
""", unsafe_allow_html=True)

# ─── 상수 ─────────────────────────────────────────────────────────────────────
AGENT_LABELS = {
    "intent": "의도 파악",
    "slot": "정보 추출",
    "execute": "이체 실행",
    "interaction": "응답 생성",
}

STAGE_KO = {
    "INIT":        ("대기 중",       "#9E9E9E"),
    "FILLING":     ("정보 수집 중",  "#1976D2"),
    "READY":       ("확인 대기",     "#F57C00"),
    "CONFIRMED":   ("승인됨",        "#00897B"),
    "EXECUTED":    ("이체 완료",     "#43A047"),
    "FAILED":      ("이체 실패",     "#E53935"),
    "CANCELLED":   ("취소됨",        "#757575"),
    "UNSUPPORTED": ("처리 불가",     "#E53935"),
}

INITIAL_MESSAGE = {
    "role": "assistant",
    "content": (
        "안녕하세요! **AI 이체 서비스**입니다. 이체를 원하시면 말씀해주세요.\n\n"
        "예시:\n"
        "- 엄마한테 50만원 보내줘\n"
        "- 홍길동 계좌로 100만원 이체해줘\n"
        "- 용걸이 1만원, 엄마한테도 2만원 보내줘 *(복수 이체)*"
    ),
}

# ─── 세션 상태 초기화 ─────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "session_id":      str(uuid.uuid4()),
        "messages":        [INITIAL_MESSAGE],
        "agent_logs":      [],
        "current_state":   None,
        "task_progress":   None,
        "batch_tasks":     [],      # [{slots, status}] — 배치 이체 전체 큐
        "pending_buttons": [],
        "pending_input":   None,
        "completed_list":  [],
        "debug_data":      {},
        "api_base":        "http://localhost:8010",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_state()


# ─── 렌더 함수들 ──────────────────────────────────────────────────────────────

def render_agent_logs(logs: list):
    if not logs:
        st.markdown("<p class='muted'>에이전트 대기 중...</p>", unsafe_allow_html=True)
        return
    parts = []
    for log in logs:
        agent = log.get("agent", "")
        label = AGENT_LABELS.get(agent, log.get("label", agent))
        result = log.get("result", "")
        status = log.get("status", "running")
        icon, css = (
            ("⏳", "agent-running") if status == "running" else
            ("✅", "agent-done")    if status == "done"    else
            ("❌", "agent-error")
        )
        extra = f"<span class='agent-result'>({result})</span>" if result else ""
        parts.append(f'<div class="agent-item {css}">{icon} {label}{extra}</div>')
    st.markdown("\n".join(parts), unsafe_allow_html=True)


def render_batch_queue(batch_tasks: list):
    """배치 이체 큐 현황 — 에이전트 패널 하단에 표시."""
    if not batch_tasks:
        return

    ICON = {"done": "✅", "failed": "❌", "executing": "⏳", "pending": "🔲"}
    CSS  = {"done": "batch-done", "failed": "batch-failed",
            "executing": "batch-exec", "pending": "batch-pending"}

    total = len(batch_tasks)
    parts = [f'<div class="batch-queue-header">배치 이체 현황 ({total}건)</div>']
    for i, task in enumerate(batch_tasks):
        slots  = task.get("slots", {})
        status = task.get("status", "pending")
        icon   = ICON.get(status, "🔲")
        css    = CSS.get(status, "batch-pending")

        target = slots.get("target") or "?"
        amount = slots.get("amount")
        amount_str = f"{amount:,}원" if amount else "?"

        parts.append(
            f'<div class="batch-item {css}">'
            f'{icon} 이체 {i + 1}/{total} — {target} · {amount_str}'
            f'</div>'
        )
    st.markdown("\n".join(parts), unsafe_allow_html=True)


def _slot_rows_html(slots: dict) -> str:
    rows = [
        ("수신자", slots.get("target") or "-"),
        ("금액",   f"{slots['amount']:,}원" if slots.get("amount") else "-"),
        ("메모",   slots.get("memo") or "-"),
        ("이체일", slots.get("transfer_date") or "-"),
    ]
    html = '<div style="margin-top:4px">'
    for label, value in rows:
        val_cls = "slot-value" if value != "-" else "slot-value slot-empty"
        html += (
            f'<div class="slot-row">'
            f'<span class="slot-label">{label}</span>'
            f'<span class="{val_cls}">{value}</span>'
            f'</div>'
        )
    return html + "</div>"


def render_transfer_state(state_snapshot):
    """현재 이체 상태 패널.
    READY + 복수 태스크: st.tabs() 로 1/N, 2/N 카드 탐색.
    """
    if not state_snapshot:
        st.markdown("<p class='muted'>진행 중인 이체 없음</p>", unsafe_allow_html=True)
        return

    stage      = state_snapshot.get("stage", "INIT")
    slots      = state_snapshot.get("slots", {})
    task_queue = state_snapshot.get("task_queue", [])
    meta       = state_snapshot.get("meta", {})
    batch_total    = meta.get("batch_total", 1)
    batch_progress = meta.get("batch_progress", 0)

    stage_ko, stage_color = STAGE_KO.get(stage, (stage, "#9E9E9E"))
    st.markdown(
        f'<span class="stage-badge" style="background:{stage_color}">{stage_ko}</span>',
        unsafe_allow_html=True,
    )

    if stage == "READY":
        all_pending = [slots] + task_queue   # 현재 태스크 + 대기 태스크
        n_pending   = len(all_pending)

        if n_pending > 1:
            # 탭 네비게이션: 이체 (P+1)/N, (P+2)/N, ...
            tab_labels = [
                f"이체 {batch_progress + i + 1}/{batch_total}"
                for i in range(n_pending)
            ]
            tabs = st.tabs(tab_labels)
            for i, (tab, task) in enumerate(zip(tabs, all_pending)):
                with tab:
                    if i == 0:
                        st.markdown(
                            "<p style='font-size:12px;color:#FF8F00;"
                            "margin:0 0 6px 0;font-weight:600'>"
                            "↑ 확인이 필요합니다</p>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(_slot_rows_html(task), unsafe_allow_html=True)
        else:
            st.markdown(_slot_rows_html(slots), unsafe_allow_html=True)
    else:
        st.markdown(_slot_rows_html(slots), unsafe_allow_html=True)
        if task_queue:
            st.markdown(
                f"<p class='muted'>대기 중인 이체: {len(task_queue)}건</p>",
                unsafe_allow_html=True,
            )


def render_task_progress(task_progress):
    """배치 실행 중 진행 상황 표시."""
    if not task_progress:
        return
    index  = task_progress.get("index", 1)
    total  = task_progress.get("total", 1)
    slots  = task_progress.get("slots", {})
    target = slots.get("target") or "?"
    amount = slots.get("amount")
    amount_str = f"{amount:,}원" if amount else "?"
    st.progress(index / total, text=f"이체 {index}/{total} 처리 중 — {target}에게 {amount_str}")


def render_completed(completed: list):
    if not completed:
        st.markdown("<p class='muted'>완료된 거래 없음</p>", unsafe_allow_html=True)
        return
    for tx in reversed(completed):   # 최신 순
        state  = tx.get("state", {})
        slots  = state.get("slots", {})
        target = slots.get("target") or "?"
        amount = slots.get("amount")
        amount_str = f"{amount:,}원" if amount else "?"
        stage  = state.get("stage", "")
        at     = tx.get("at", "")[:19].replace("T", " ")
        memo   = slots.get("memo") or ""

        stage_ko, _ = STAGE_KO.get(stage, (stage, "#9E9E9E"))
        extra_css   = ("" if stage == "EXECUTED" else
                       "tx-failed" if stage == "FAILED" else "tx-cancelled")
        detail      = " · ".join(filter(None, [stage_ko, at]))
        memo_line   = f"<div class='tx-memo'>메모: {memo}</div>" if memo else ""

        st.markdown(
            f'<div class="tx-card {extra_css}">'
            f"<div style='font-weight:600'>{target} · {amount_str}</div>"
            f"<div class='tx-detail'>{detail}</div>"
            f"{memo_line}"
            f"</div>",
            unsafe_allow_html=True,
        )


def render_memory_debug(debug_data: dict):
    """메모리 / 세션 내부 상태 (개발용)."""
    if not debug_data:
        st.caption("디버그 데이터 없음 (백엔드 DEV_MODE=true 확인)")
        return

    memory = debug_data.get("memory", {})
    state  = debug_data.get("state", {})

    turns   = memory.get("raw_history_turns", 0)
    summary = memory.get("summary_text", "")
    st.markdown(f"**대화 턴:** {turns}턴 누적")
    if summary:
        st.markdown(f"**요약:**\n> {summary}")

    with st.expander("state JSON", expanded=False):
        st.json(state)

    history = memory.get("raw_history", [])
    if history:
        with st.expander(f"raw_history ({len(history)}개)", expanded=False):
            for msg in history:
                role = "🧑" if msg.get("role") == "user" else "🤖"
                st.markdown(f"{role} {msg.get('content', '')}")


# ─── 배치 태스크 상태 헬퍼 ────────────────────────────────────────────────────

def _rebuild_batch_tasks(final_state: dict, prev_batch_tasks: list) -> list:
    """DONE 이벤트 후 batch_tasks 재구성."""
    if not final_state:
        return []

    stage          = final_state.get("stage", "INIT")
    meta           = final_state.get("meta", {})
    batch_total    = meta.get("batch_total", 1)
    batch_progress = meta.get("batch_progress", 0)
    slots          = final_state.get("slots", {})
    task_queue     = final_state.get("task_queue", [])

    if stage == "INIT":
        return []

    if batch_total <= 1:
        return []

    # 완료된 태스크: prev_batch_tasks 앞쪽 batch_progress 개를 "done"으로
    done_tasks = []
    for i in range(batch_progress):
        prev_slots = prev_batch_tasks[i]["slots"] if i < len(prev_batch_tasks) else {}
        done_tasks.append({"slots": prev_slots, "status": "done"})

    # 현재 태스크 (확인 대기)
    current_task = [{"slots": slots, "status": "pending"}] if slots else []

    # 대기 중인 태스크
    queued_tasks = [{"slots": t, "status": "pending"} for t in task_queue]

    return done_tasks + current_task + queued_tasks


# ─── 사이드바 ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")
    new_url = st.text_input("백엔드 서버 URL", value=st.session_state.api_base)
    if new_url != st.session_state.api_base:
        st.session_state.api_base = new_url

    st.divider()
    st.caption(f"세션 ID: `{st.session_state.session_id[:8]}...`")
    if st.button("🔄 새 대화 시작", use_container_width=True):
        for key in ("messages", "agent_logs", "current_state", "task_progress",
                    "batch_tasks", "pending_buttons", "pending_input",
                    "completed_list", "debug_data"):
            st.session_state.pop(key, None)
        st.session_state.session_id = str(uuid.uuid4())
        _init_state()
        st.rerun()

    st.divider()
    st.caption("**테스트 예시**")
    examples = [
        "엄마한테 50만원 보내줘",
        "홍길동에게 100만원 이체해줘",
        "용걸이 1만원, 엄마한테도 2만원 보내줘",
        "10000원을 5번 보내려 해 친구한테",
        "날씨 어때?",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
            st.session_state.pending_input = ex
            st.session_state.pending_buttons = []
            st.rerun()


# ─── 메인 레이아웃 ────────────────────────────────────────────────────────────
st.title("🏦 AI 이체 서비스")

chat_col, info_col = st.columns([3, 2], gap="large")

# ── 오른쪽 패널 ────────────────────────────────────────────────────────────────
with info_col:
    st.subheader("에이전트 진행 상황")
    agent_progress_ph = st.empty()
    with agent_progress_ph:
        render_agent_logs(st.session_state.agent_logs)

    # 배치 큐 (항상 placeholder 확보; 데이터 있을 때만 내용 채움)
    batch_queue_ph = st.empty()
    if st.session_state.batch_tasks:
        with batch_queue_ph:
            render_batch_queue(st.session_state.batch_tasks)

    # 배치 실행 진행바
    task_progress_ph = st.empty()
    if st.session_state.task_progress:
        with task_progress_ph:
            render_task_progress(st.session_state.task_progress)

    st.divider()

    st.subheader("현재 이체 정보")
    # st.empty() 없이 직접 렌더 → st.tabs() 사용 가능
    render_transfer_state(st.session_state.current_state)

    st.divider()

    st.subheader("완료된 거래")
    completed_ph = st.empty()
    with completed_ph:
        render_completed(st.session_state.completed_list)

    st.divider()

    with st.expander("🔍 메모리 디버그 (개발용)", expanded=False):
        render_memory_debug(st.session_state.debug_data)


# ── 왼쪽 패널 (채팅) ──────────────────────────────────────────────────────────
with chat_col:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── 처리 중 ───────────────────────────────────────────────────────────────
    if st.session_state.pending_input:
        user_msg = st.session_state.pending_input
        st.session_state.pending_input = None
        st.session_state.task_progress = None

        with st.chat_message("user"):
            st.markdown(user_msg)
        with st.chat_message("assistant"):
            response_ph = st.empty()
            response_ph.markdown("생각 중... ⏳")

        agent_logs: list  = []
        batch_tasks: list = list(st.session_state.batch_tasks)  # 이전 턴에서 이어받기
        full_text         = ""
        final_message     = ""
        final_state       = None
        final_buttons:list = []

        try:
            for event_type, data in stream_chat(
                st.session_state.session_id, user_msg, st.session_state.api_base
            ):
                # ── AGENT_START ──────────────────────────────────────────────
                if event_type == "AGENT_START":
                    agent_name = data.get("agent", "")
                    agent_logs = [l for l in agent_logs if l["agent"] != agent_name]
                    agent_logs.append({
                        "agent": agent_name,
                        "label": data.get("label", ""),
                        "status": "running",
                    })
                    with agent_progress_ph:
                        render_agent_logs(agent_logs)

                # ── AGENT_DONE ───────────────────────────────────────────────
                elif event_type == "AGENT_DONE":
                    agent_name = data.get("agent", "")
                    success    = data.get("success", True)
                    for log in agent_logs:
                        if log["agent"] == agent_name:
                            log["status"] = "done" if success else "error"
                            if data.get("result"):
                                log["result"] = str(data["result"])
                    with agent_progress_ph:
                        render_agent_logs(agent_logs)

                    # execute 완료 → 실행 중이던 태스크 상태 업데이트
                    if agent_name == "execute" and batch_tasks:
                        for task in batch_tasks:
                            if task.get("status") == "executing":
                                task["status"] = "done" if success else "failed"
                                break
                        with batch_queue_ph:
                            render_batch_queue(batch_tasks)

                # ── TASK_PROGRESS ────────────────────────────────────────────
                elif event_type == "TASK_PROGRESS":
                    st.session_state.task_progress = data
                    with task_progress_ph:
                        render_task_progress(data)

                    # 첫 번째 pending 태스크를 executing으로 전환
                    for task in batch_tasks:
                        if task.get("status") == "pending":
                            task["status"] = "executing"
                            break
                    with batch_queue_ph:
                        render_batch_queue(batch_tasks)

                # ── LLM_TOKEN ────────────────────────────────────────────────
                elif event_type == "LLM_TOKEN":
                    token = data if isinstance(data, str) else data.get("payload", "")
                    full_text += token
                    response_ph.markdown(full_text + "▌")

                # ── DONE ─────────────────────────────────────────────────────
                elif event_type == "DONE":
                    final_message = data.get("message") or full_text
                    response_ph.markdown(final_message)
                    final_state   = data.get("state_snapshot") or {}
                    final_buttons = data.get("ui_hint", {}).get("buttons", [])

                    # task_progress 초기화
                    st.session_state.task_progress = None
                    task_progress_ph.empty()

                    # batch_tasks 재구성
                    batch_tasks = _rebuild_batch_tasks(final_state, batch_tasks)
                    with batch_queue_ph:
                        render_batch_queue(batch_tasks)

        except (ConnectionError, TimeoutError, RuntimeError) as e:
            error_msg = f"❌ {e}"
            response_ph.markdown(error_msg)
            final_message = error_msg

        # ── 상태 저장 + 완료 거래 / 메모리 갱신 ──────────────────────────────
        st.session_state.messages.append({"role": "user", "content": user_msg})
        st.session_state.messages.append({"role": "assistant", "content": final_message})
        st.session_state.agent_logs   = agent_logs
        st.session_state.current_state = final_state
        st.session_state.batch_tasks  = batch_tasks
        st.session_state.pending_buttons = final_buttons

        st.session_state.completed_list = get_completed(
            st.session_state.session_id, st.session_state.api_base
        )
        st.session_state.debug_data = get_debug(
            st.session_state.session_id, st.session_state.api_base
        )

        st.rerun()

    # ── 액션 버튼 ─────────────────────────────────────────────────────────────
    if st.session_state.pending_buttons:
        btn_cols = st.columns(len(st.session_state.pending_buttons))
        for i, btn_text in enumerate(st.session_state.pending_buttons):
            with btn_cols[i]:
                if st.button(
                    btn_text,
                    key=f"action_{i}_{btn_text}",
                    use_container_width=True,
                    type="primary" if i == 0 else "secondary",
                ):
                    st.session_state.pending_input = btn_text
                    st.session_state.pending_buttons = []
                    st.rerun()

    # ── 채팅 입력 ──────────────────────────────────────────────────────────────
    if prompt := st.chat_input("메시지를 입력하세요..."):
        st.session_state.pending_input = prompt
        st.session_state.pending_buttons = []
        st.rerun()
