#!/usr/bin/env bash
# uvicorn(api_server) 재시작 — --reload 상시가동 대신 코드 수정 후 수동/버튼 트리거로만 재기동.
# 대시보드 "업데이트" 버튼(api_server/router_autopilot.py: /alpaca/update/execute)이
# 이 스크립트를 detached로 실행.
#
# com.seokminal.api.plist(KeepAlive=true)가 이 프로세스를 launchd로 관리 중(2026-09-02~03
# 무인운영 대비 작업에서 등록됨). kill만 하면 launchd가 자동으로 새로 띄운다 — 여기서
# 직접 nohup으로 재기동까지 하면 launchd 자동재기동과 포트 bind 경합이 생겨(2026-09-03
# 실측: "address already in use"로 이쪽이 매번 짐, 서버 자체는 launchd가 살려서 안 죽었지만
# 로그에 오해 소지 있는 에러가 남음) 이제 kill만 하고 launchd 재기동을 기다린다.
set -e
cd "$(dirname "$0")/.."
PORT=8000
mkdir -p logs

echo "[restart_api] $(date '+%F %T') 기존 uvicorn(:$PORT) 종료 — launchd(KeepAlive)가 자동 재기동함"
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true

for _ in $(seq 1 20); do
    sleep 1
    curl -sf -m 2 http://127.0.0.1:$PORT/health >/dev/null 2>&1 && break
done
echo "[restart_api] $(date '+%F %T') 완료 (health: $(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health 2>/dev/null || echo down))"
