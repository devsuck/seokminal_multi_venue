#!/usr/bin/env bash
# 죽은 tmux 수집기 세션을 재생성 — 맥에서 launchd가 주기(StartInterval=60) 실행.
#
# 비침습 설계: HUD의 tmux 기반 생존체크(_tmux_process_status)와 재시작 버튼을 그대로
# 보존한다. 세션명은 lab_api.py COLLECTOR_SESSIONS와 동일, 세션이 *없을 때만* 생성하므로
# 살아있는 세션은 안 건드림. 잠자기/크래시/재부팅 후 죽은 것만 되살아난다.
#
# 수동 검증(launchd 걸기 전):
#   SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
#     bash scripts/deploy/ensure_collectors.sh
#   tmux ls   # 세션들 떠야 함
set -u

# launchd는 PATH가 최소라 tmux/python을 못 찾을 수 있음 — 흔한 위치 보강.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${SEOKMINAL_PYTHON:-python3}"
cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }

# 상시 유지할 수집기(세션명  모듈). 안 돌릴 것은 줄 삭제/주석 처리 — 이게 desired state.
# (launchd가 매분 이 목록대로 죽은 것만 되살림)
ENSURE=(
  "hl-orderflow-tick|research.run_hl_orderflow_tick_collect"
  "cross-venue-skew-tick|research.run_cross_venue_skew_collect"
  "convergence-legs|research.run_convergence_signal_collect"
)

for entry in "${ENSURE[@]}"; do
  session="${entry%%|*}"
  module="${entry##*|}"
  if tmux has-session -t "$session" 2>/dev/null; then
    continue  # 이미 살아있음 — 안 건드림
  fi
  # tmux new-session은 서버가 들고 있는 환경 스냅샷을 쓰지, 이 스크립트가 export한 값을
  # 물려받지 않음 — .env 소싱은 새 세션 안에서 직접 해야 한다.
  tmux new-session -d -s "$session" bash -c \
    "cd '$REPO_ROOT' && set -a && [ -f .env ] && source .env; set +a; exec '$PY' -m '$module'" \
    && echo "$(date '+%F %T') 재생성: $session ($module)" \
    || echo "$(date '+%F %T') 재생성 실패: $session" >&2
done
