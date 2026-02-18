#!/usr/bin/env bash
# scripts/backend.sh — FastAPI 백엔드 실행
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── 설정 (환경 변수로 덮어쓰기 가능) ─────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8010}"
LOG_LEVEL="${LOG_LEVEL:-info}"
RELOAD="${RELOAD:-true}"

# ── 컬러 ──────────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${CYAN}  Backend  │  http://$HOST:$PORT${RESET}"
echo -e "${CYAN}  API Docs │  http://localhost:$PORT/docs${RESET}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Reload   : ${YELLOW}$RELOAD${RESET}   Log: ${YELLOW}$LOG_LEVEL${RESET}"
echo ""

# ── .env 존재 확인 ────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  echo -e "${YELLOW}[warn] .env 없음. OPENAI_API_KEY 등이 설정되지 않을 수 있어요.${RESET}"
fi

# ── 실행 ──────────────────────────────────────────────────────────────────────
RELOAD_FLAG=""
[ "$RELOAD" = "true" ] && RELOAD_FLAG="--reload"

exec uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --log-level "$LOG_LEVEL" \
  $RELOAD_FLAG
