#!/usr/bin/env bash
# 오디세이(Odyssey) — buyback v1 순수형(균등weight, 사이징blend 없음) paper trading. SIREN 대조군, 평일 매일 실행.
# 기록만 — 실주문 없음, live 전환 없음(그건 사람이 별도 결정).
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/run_odyssey_forward.sh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

set -a
[ -f .env ] && source .env
set +a

PYTHONPATH=. "$PY" -m research.paper.odyssey_forward
