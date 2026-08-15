#!/bin/bash
# options_uoa 사후수익률 라벨러 실행 후 라벨 n을 macOS 알림으로 띄운다.
# crontab에서 부르므로 PATH/cwd를 가정하지 않는다.
# 수동 실행: bash scripts/options_uoa_n_check.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
LOG="$REPO/research/data/options_uoa_forward/n_check.log"
mkdir -p "$(dirname "$LOG")"

cd "$REPO" || exit 1
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
  PYTHONPATH=. "$PY" research/run_options_uoa_forward.py 2>&1
} | tee -a "$LOG"

# 마지막 실행 블록에서 fwd_5d n 추출 (없으면 0)
N=$(grep -o 'fwd_5d: n=[0-9]*' "$LOG" | tail -1 | grep -o '[0-9]*$')
N=${N:-0}
if [ "$N" -ge 30 ]; then
  MSG="신호 n=$N — 임계값 스윕 가능"
else
  MSG="신호 n=$N — 30 미만, 스윕 보류"
fi
osascript -e "display notification \"$MSG\" with title \"options_uoa 사후수익률\"" 2>/dev/null
echo "$MSG"
