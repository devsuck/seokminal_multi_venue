#!/usr/bin/env bash
# buyback v3 CB/BW 희석오버행 shadow 필터 forward 체크 — launchd가 주 1회 실행.
# in-sample vs forward(FROZEN_DATE 이후) net/승률 비교를 ledger에 스냅샷 append.
# 기록만 — v1 동결 그대로, 승격/live 전환 없음(그건 사람이 별도 결정).
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/run_buyback_v3_forward.sh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

set -a
[ -f .env ] && source .env
set +a

PYTHONPATH=. "$PY" -m research.paper.buyback_v3_dilution_forward --write
