#!/usr/bin/env bash
# Research Capture 배치(P205 Edge Score 표본 축적) — launchd가 평일 1회(StartCalendarInterval) 실행.
# 추적 전략(paper_active/watchlist/paper_candidate)의 현재 위원회 평가를 예측 레지스트리에
# 사전등록한다(중복 skip, 멱등). 기록만 — 거래·집행·전략 승격 없음(그건 사람이 별도 결정).
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/run_research_capture.sh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

set -a
[ -f .env ] && source .env
set +a

PYTHONPATH=. "$PY" research/run_research_capture.py
