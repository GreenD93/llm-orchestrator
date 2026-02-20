#!/usr/bin/env bash
# scripts/frontend.sh — Streamlit 프론트엔드 실행
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── .env 로드 ──────────────────────────────────────────────────────────────────
[ -f "$ROOT/.env" ] && set -a && source "$ROOT/.env" && set +a

# ── 설정 (.env → 환경 변수 → 기본값 순서로 적용) ──────────────────────────────
FRONTEND_PORT="${FRONTEND_PORT:-8501}"
BACKEND_URL="${BACKEND_URL:-http://localhost:${BACKEND_PORT:-8010}}"

# ── 컬러 ──────────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${CYAN}  Frontend   │  http://localhost:$FRONTEND_PORT${RESET}"
echo -e "${CYAN}  Backend    │  $BACKEND_URL${RESET}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

# ── 백엔드 응답 확인 ──────────────────────────────────────────────────────────
echo -n "  백엔드 연결 확인... "
if curl -sf --max-time 2 "$BACKEND_URL/docs" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ 연결됨${RESET}"
else
  echo -e "${YELLOW}⚠ 응답 없음${RESET}"
  echo -e "  ${YELLOW}→ scripts/backend.sh 를 먼저 실행했는지 확인하세요.${RESET}"
  echo -e "  ${YELLOW}  사이드바에서 백엔드 URL을 직접 변경할 수도 있어요.${RESET}"
fi
echo ""

# ── 실행 ──────────────────────────────────────────────────────────────────────
exec streamlit run frontend/app.py \
  --server.port "$FRONTEND_PORT" \
  --server.address localhost \
  --server.headless true \
  --browser.gatherUsageStats false
