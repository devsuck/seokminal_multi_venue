#!/usr/bin/env bash
# uvicorn(api_server) 재시작 — --reload 상시가동 대신 코드 수정 후 수동/버튼 트리거로만 재기동.
# 대시보드 "업데이트" 버튼(api_server/router_autopilot.py: /alpaca/update/execute)이
# 이 스크립트를 detached로 실행 — 스크립트가 자기 부모(현재 떠있는 uvicorn 자신 포함)를
# 포트 기준으로 죽이고 새로 띄우므로 부모가 먼저 죽어도 계속 진행된다.
set -e
cd "$(dirname "$0")/.."
PORT=8000
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
mkdir -p logs

echo "[restart_api] $(date '+%F %T') 기존 uvicorn(:$PORT) 종료"
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
sleep 1

echo "[restart_api] $(date '+%F %T') 재기동 (no --reload)"
nohup "$PY" -m uvicorn api_server.main:app --timeout-graceful-shutdown 10 \
  >> logs/api_server.log 2>&1 &
disown
echo "[restart_api] 완료 PID $!"
