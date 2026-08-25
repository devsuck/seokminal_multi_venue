"""생성된 SignalFn 코드 스모크체크 — 크래시/전부-False/NaN 여부만 확인하는
싼 필터. 통계적 유의미성은 여기서 안 봄(그건 run_paper_hypothesis_validate.py
+ runner.py 엔진 몫). fixture OHLC는 합성 데이터 — exec 안전성 확인용."""
from __future__ import annotations

import math

REQUIRED_SYMBOLS = ("NAME", "DESCRIPTION", "signal_fn")


def _fixture_ohlc(n: int = 200) -> dict:
    close = [100.0 + (i % 20) * 0.5 - (i % 7) * 0.3 for i in range(n)]
    high = [c + 0.5 for c in close]
    low = [c - 0.5 for c in close]
    open_ = [c - 0.1 for c in close]
    volume = [1000.0 + (i % 10) * 50 for i in range(n)]
    ts = list(range(n))
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "ts": ts}


def _fixture_feat(ohlc: dict) -> dict:
    n = len(ohlc["close"])
    close = ohlc["close"]
    # vwap을 close와 동일하게 두면 dev=(c-vwap)/vwap이 항상 0이 되어 VWAP
    # 이탈 기반 시그널(예: vwap_mean_reversion)이 절대 트리거되지 않는다.
    # close 대비 소폭(±1%) 주기적 오프셋을 줘서 dev_k=0.004 같은 임계값을
    # 실제로 넘나드는 바가 섞이도록 한다.
    vwap = [close[i] * (1 + 0.01 * math.sin(i * 0.9)) for i in range(n)]
    return {
        "sids": [0] * n,
        "mso": [float(i % 390) for i in range(n)],
        "vwap": vwap,
        "atr_abs": [1.0] * n,
    }


def check(code: str) -> tuple[bool, str]:
    namespace: dict = {}
    try:
        exec(code, namespace)
    except Exception as e:
        return False, f"exec 실패: {e}"

    missing = [s for s in REQUIRED_SYMBOLS if s not in namespace]
    if missing:
        return False, f"필수 심볼 누락: {missing}"

    signal_fn = namespace["signal_fn"]
    ohlc = _fixture_ohlc()
    feat = _fixture_feat(ohlc)
    try:
        result = signal_fn(ohlc, feat, {}, {})
    except Exception as e:
        return False, f"signal_fn 실행 실패: {e}"

    if not isinstance(result, dict) or "entry" not in result or "eligible" not in result:
        return False, "signal_fn 반환값에 entry/eligible 키 없음"

    try:
        n_expected = len(ohlc["close"])
        entry = result["entry"]
        if len(entry) != n_expected:
            return False, f"entry 길이 불일치: {len(entry)} != {n_expected}"
        if any(e is None for e in entry):
            return False, "entry에 None 포함(bool이어야 함)"
        if any(isinstance(e, float) and math.isnan(e) for e in entry):
            return False, "entry에 NaN 포함"
        if not any(entry):
            return False, "entry 전부 False — 시그널 없음"
        if all(entry):
            return False, "entry 전부 True — 상수 시그널"

        # eligible = opportunity set(전체 바 중 전제조건이 성립한 바의 인덱스
        # 목록) — n_expected와 길이가 같아야 하는 게 아니라 그 부분집합이면
        # 됨(runner.py/strategies.py 실제 가설들이 다 이런 형태). 그래도
        # 전체 바 수를 넘을 수는 없고, 각 원소는 유효한 바 인덱스여야 한다.
        eligible = result["eligible"]
        if len(eligible) > n_expected:
            return False, f"eligible 길이 초과: {len(eligible)} > {n_expected} (opportunity set이 전체 바 수를 넘을 수 없음)"
        if any(not isinstance(e, int) for e in eligible):
            return False, "eligible 타입 오류: int가 아닌 원소 포함"
        if any(not (0 <= e < n_expected) for e in eligible):
            return False, f"eligible 인덱스 범위 오류: 0 <= e < {n_expected} 벗어난 원소 포함"
        # entry=True인 인덱스는 반드시 eligible(opportunity set) 안에 있어야 함 —
        # 아니면 runner.py의 랜덤베이스라인이 잘못된 기회집합에서 샘플링해 p-value가 왜곡된다.
        entry_true_idx = {i for i, e in enumerate(entry) if e}
        if not entry_true_idx.issubset(eligible):
            return False, "entry=True인 인덱스가 eligible(opportunity set) 밖에 있음"
    except Exception as e:
        return False, f"반환값 검증 실패: {e}"

    return True, ""
