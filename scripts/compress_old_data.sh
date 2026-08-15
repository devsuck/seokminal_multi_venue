#!/bin/bash
# research/data/ 밑 오래된 raw jsonl을 gzip 압축 — 디스크 무제한 증가 방지.
# crontab에서 매일 새벽 부름. PATH/cwd 가정 안 함.
# 수동 실행: bash scripts/compress_old_data.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
LOG="$REPO/logs/compress_old_data.log"
mkdir -p "$(dirname "$LOG")"

cd "$REPO" || exit 1
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
  "$PY" -m research.compress_old_data 2>&1
} >> "$LOG" 2>&1
