#!/usr/bin/env bash
# 논문-알파-마이닝 파이프라인 주기 실행 루프.
# 신규논문 없으면 LLM 콜 자체가 안 나감(커서 dedup) — 매 사이클 비용 걱정 없음.
set -euo pipefail
cd "$(dirname "$0")/.."

INTERVAL_SEC="${PAPER_INGEST_INTERVAL_SEC:-21600}"  # 기본 6시간

while true; do
  echo "[$(date -u +%FT%TZ)] run_paper_ingest 시작"
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m research.run_paper_ingest || echo "[$(date -u +%FT%TZ)] 실행 실패, 다음 사이클에 재시도"
  echo "[$(date -u +%FT%TZ)] ${INTERVAL_SEC}초 대기"
  sleep "$INTERVAL_SEC"
done
