#!/usr/bin/env bash
# 오라클(또는 임의 리눅스 ARM) VM 부트스트랩 — seokminal_multi_venue 백엔드 상시구동용.
#
# 전제: Ubuntu 24.04 LTS (aarch64/ARM Ampere A1) 권장. Python >=3.11 필요
#       (pyproject 요구사항). Ubuntu 22.04는 기본 python이 3.10이라 부적합 —
#       24.04(python3.12) 쓰거나 deadsnakes로 3.11+ 별도 설치할 것.
#
# 실행(레포 루트에서):
#   git clone <this-repo> ~/seokminal_multi_venue
#   cd ~/seokminal_multi_venue
#   bash scripts/deploy/setup_server.sh
#
# nautilus_trader 버전 이슈: 로컬(맥)에서 검증된 버전으로 핀하는 게 안전하다.
#   맥에서:  pip freeze > requirements.lock   후 이 파일을 VM 레포 루트로 복사하면
#   이 스크립트가 -e . 대신 requirements.lock을 우선 사용한다. 없으면 pyproject로 설치.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
echo "[setup] repo root: $REPO_ROOT"

# --- 1. 시스템 패키지 -------------------------------------------------------
echo "[setup] apt 패키지 설치..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip \
    build-essential git curl rsync ca-certificates tmux

# --- 2. Python 버전 확인 (>=3.11) ------------------------------------------
PYBIN="${PYBIN:-python3}"
PYVER="$("$PYBIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "[setup] python: $PYBIN ($PYVER)"
"$PYBIN" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)' || {
    echo "[setup] ❌ Python $PYVER < 3.11. Ubuntu 24.04를 쓰거나 PYBIN=python3.12 등으로 지정하세요." >&2
    exit 1
}

# --- 3. 가상환경 + 의존성 ---------------------------------------------------
if [ ! -d .venv ]; then
    echo "[setup] venv 생성..."
    "$PYBIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip wheel

if [ -f requirements.lock ]; then
    echo "[setup] requirements.lock 발견 — 로컬 검증 버전으로 설치(권장 경로)"
    pip install -r requirements.lock
    pip install -e . --no-deps   # 로컬 패키지 자체만 editable 등록(의존성은 lock이 고정)
else
    echo "[setup] requirements.lock 없음 — pyproject로 설치(nautilus 버전 드리프트 주의)"
    echo "[setup] 안전하게 하려면 맥에서 'pip freeze > requirements.lock' 후 재실행 권장"
    pip install -e ".[dev]"
fi

# --- 4. 임포트 스모크 테스트 ------------------------------------------------
echo "[setup] 임포트 스모크 테스트..."
python - <<'PY'
mods = ["pandas", "numpy", "requests", "websockets"]
for m in mods:
    __import__(m); print(f"  ok: {m}")
# nautilus는 API/백테스트용 — 파일럿 수집기엔 불필요하지만 전체 이전 대비 확인
try:
    import nautilus_trader  # noqa: F401
    print("  ok: nautilus_trader")
except Exception as e:  # noqa: BLE001
    print(f"  ⚠️  nautilus_trader import 실패(파일럿 수집기엔 무관, 전체이전 전 해결 필요): {type(e).__name__}: {e}")
PY

# --- 5. 로그 디렉토리 -------------------------------------------------------
mkdir -p logs

echo ""
echo "[setup] ✅ 완료. 다음 단계:"
echo "  1) .env 생성(맥에서 복사 또는 재작성) — KIS/DART/FRED 등 키"
echo "  2) KIS 해외IP 관문 검증:  python scripts/deploy/test_kis_connectivity.py"
echo "  3) 파일럿 서비스 등록:     docs/deploy/oracle-pilot.md 4단계 참고"
