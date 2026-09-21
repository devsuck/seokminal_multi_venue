#!/usr/bin/env bash
# SIREN(KR buyback drift paper trading) 일일 체크 — launchd가 평일 매일 실행.
# 신규 자사주 이벤트 진입/HOLD일 경과분 청산 시뮬레이션 후 state/ledger/report 갱신.
# 기록만 — 실주문 없음, live 전환 없음(그건 사람이 별도 결정).
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/run_siren_forward.sh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

set -a
[ -f .env ] && source .env
set +a

PYTHONPATH=. "$PY" -m research.paper.siren_forward
