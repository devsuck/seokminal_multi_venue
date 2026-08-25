#!/usr/bin/env bash
# 오토리서치 배치(팩터/이벤트 후보 발굴) — launchd가 주 1회(StartCalendarInterval) 실행.
# 결과는 research/autoresearch/{status.json,results.jsonl}에 누적. 실행 자체는
# 읽기전용 리서치이며 어떤 전략도 자동 FROZEN/paper 승격하지 않음(그건 별도 사람 판단).
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/run_autoresearch.sh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

set -a
[ -f .env ] && source .env
set +a

PYTHONPATH=. "$PY" research/run_autoresearch.py
