#!/bin/bash
# research/data/ 밑 90일 지난 파일(원본+.gz) 실제 삭제 — 압축은 무한증가만 늦추지 막지는 않음.
# crontab에서 매일 새벽 부름. PATH/cwd 가정 안 함.
# 수동 실행: bash scripts/prune_old_data.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
LOG="$REPO/logs/prune_old_data.log"
mkdir -p "$(dirname "$LOG")"

cd "$REPO" || exit 1
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
  "$PY" -m research.prune_old_data 2>&1
} >> "$LOG" 2>&1
