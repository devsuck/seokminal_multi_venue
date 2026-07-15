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
    return {
        "sids": [0] * n,
        "mso": [float(i % 390) for i in range(n)],
        "vwap": list(ohlc["close"]),
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

    entry = result["entry"]
    if len(entry) != len(ohlc["close"]):
        return False, f"entry 길이 불일치: {len(entry)} != {len(ohlc['close'])}"
    if any(e is None for e in entry):
        return False, "entry에 None 포함(bool이어야 함)"
    if any(isinstance(e, float) and math.isnan(e) for e in entry):
        return False, "entry에 NaN 포함"
    if not any(entry):
        return False, "entry 전부 False — 시그널 없음"

    return True, ""
