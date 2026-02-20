#!/bin/bash
# AI 이체 서비스 - 백엔드 + 프론트엔드 동시 실행 (.env에서 포트 설정)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── .env 로드 ─────────────────────────────────────────────────────────────────
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo ".env 로드 완료"
else
    echo "경고: .env 파일 없음 (.env.example을 참고해 생성하세요)"
fi

BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-8501}"

# ── 기존 프로세스 정리 ────────────────────────────────────────────────────────
echo "기존 프로세스 정리 중..."
lsof -ti tcp:$BACKEND_PORT  | xargs kill -9 2>/dev/null
lsof -ti tcp:$FRONTEND_PORT | xargs kill -9 2>/dev/null
sleep 1

# ── 백엔드 실행 ───────────────────────────────────────────────────────────────
echo "백엔드 시작 중 (포트 $BACKEND_PORT)..."
python3 -m uvicorn app.main:app --reload --port $BACKEND_PORT > logs/backend.log 2>&1 &
BACKEND_PID=$!

# ── 프론트엔드 실행 ───────────────────────────────────────────────────────────
echo "프론트엔드 시작 중 (포트 $FRONTEND_PORT)..."
python3 -m streamlit run frontend/app.py \
    --server.port $FRONTEND_PORT \
    --server.headless true \
    > logs/frontend.log 2>&1 &
FRONTEND_PID=$!

# ── 헬스 체크 ─────────────────────────────────────────────────────────────────
echo "서버 대기 중..."
for i in $(seq 1 10); do
    sleep 1
    BACKEND_OK=false
    FRONTEND_OK=false
    curl -sf http://localhost:$BACKEND_PORT/docs  > /dev/null 2>&1 && BACKEND_OK=true
    curl -sf http://localhost:$FRONTEND_PORT      > /dev/null 2>&1 && FRONTEND_OK=true
    $BACKEND_OK && $FRONTEND_OK && break
done

echo ""
echo "──────────────────────────────────────────"
$BACKEND_OK  && echo "  백엔드   ✅  http://localhost:$BACKEND_PORT"  || echo "  백엔드   ❌  실패 (logs/backend.log 확인)"
$FRONTEND_OK && echo "  프론트엔드 ✅  http://localhost:$FRONTEND_PORT" || echo "  프론트엔드 ❌  실패 (logs/frontend.log 확인)"
echo "──────────────────────────────────────────"
echo "  종료: Ctrl+C"
echo ""

# ── 종료 시 자식 프로세스 정리 ────────────────────────────────────────────────
cleanup() {
    echo ""
    echo "서버 종료 중..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "종료 완료"
}
trap cleanup EXIT INT TERM

wait
