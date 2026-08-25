#!/usr/bin/env bash
# 일일 성과 요약 텔레그램 발송 — launchd가 하루 1회(StartCalendarInterval) 실행.
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/run_daily_summary.sh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

set -a
[ -f .env ] && source .env
set +a

"$PY" -m api_server.daily_summary
