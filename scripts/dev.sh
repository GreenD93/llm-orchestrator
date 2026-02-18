#!/usr/bin/env bash
# scripts/dev.sh — 백엔드 + 프론트엔드 동시 실행 (개발용)
# Ctrl+C 하면 두 프로세스 모두 종료됨
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"

CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${CYAN}  Dev Mode — Backend + Frontend${RESET}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  ${YELLOW}Ctrl+C 로 전체 종료${RESET}"
echo ""

# 자식 프로세스 그룹 전체 종료
cleanup() {
  echo ""
  echo -e "${YELLOW}종료 중...${RESET}"
  kill 0
}
trap cleanup INT TERM

# 백엔드 (로그 prefix 추가)
bash "$SCRIPTS/backend.sh" 2>&1 | sed 's/^/[backend] /' &
BACKEND_PID=$!

# 백엔드 기동 대기 (최대 10초)
echo -n "  백엔드 기동 대기"
for i in $(seq 1 10); do
  sleep 1
  if curl -sf --max-time 1 "http://localhost:${PORT:-8010}/docs" > /dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  if [ "$i" -eq 10 ]; then
    echo " (타임아웃, 프론트엔드 계속 실행)"
  fi
done

# 프론트엔드 (로그 prefix 추가)
bash "$SCRIPTS/frontend.sh" 2>&1 | sed 's/^/[frontend] /' &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
