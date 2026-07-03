"""KR 횡단면 팩터 엔진 — 합성 데이터로 수학 검증(심은 효과 탐지·무효과≈중앙).

사전등록 3팩터(size·amihud·turnover)만. momentum/reversal/sector=기각, low_vol=WEAK
(같은 PIT 데이터로 기검증) → 엔진에 없어야 함(재실험 금지).
"""
from __future__ import annotations

import math
import random

from research.autoresearch.engines_factor import FACTORS, factor_candidates, run_factor


def _synth_series(n_stocks=80, n_days=420, size_effect=0.0, seed=7):
    """합성 시리즈 — code가 작을수록 시총 작게. size_effect>0이면 소형주에 일드리프트 심음."""
    rng = random.Random(seed)
    out = {}
    base = "2024-01-01"
    # 거래일: 평일 흉내(연속 날짜로 충분 — 월 경계만 중요)
    import datetime as dt
    d0 = dt.date(2024, 1, 2)
    dates = []
    d = d0
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    for i in range(n_stocks):
        mcap = 1e10 * (1 + i * 3)          # i 작음 = 소형
        drift = size_effect * (1 - i / n_stocks)  # 소형일수록 드리프트 큼
        px = 1000.0
        closes, tvals, mcaps = [], [], []
        for _ in dates:
            px *= math.exp(drift + rng.gauss(0, 0.02))
            closes.append(round(px, 2))
            tvals.append(1e8 * (1 + i))     # 소형 = 거래대금 작음
            mcaps.append(mcap)
        out[f"{i:06d}"] = {"dates": list(dates), "close": closes, "tval": tvals, "marcap": mcaps}
    return out


def test_preregistered_slate_only():
    assert set(FACTORS) == {"kr_size_smb", "kr_amihud_illiq", "kr_turnover_neglect"}
    for fid in ("kr_momentum", "kr_reversal", "kr_low_vol"):  # 기각/기검증 재실험 금지
        assert not any(fid in k for k in FACTORS)


def test_planted_size_effect_detected():
    s = _synth_series(size_effect=0.004, seed=11)
    r = run_factor("kr_size_smb", s, n_perms=120)
    assert r is not None
    assert r["net"] > 0
    assert r["percentile"] >= 90  # 심은 효과 → 상위


def test_no_effect_near_random():
    s = _synth_series(size_effect=0.0, seed=13)
    r = run_factor("kr_size_smb", s, n_perms=120)
    assert r is not None
    assert 5 <= r["percentile"] <= 95  # 무효과 → 극단 아님


def test_underpowered_returns_none():
    s = _synth_series(n_stocks=10, n_days=80)  # 종목·월 부족
    assert run_factor("kr_size_smb", s, n_perms=50) is None


def test_candidates_enter_batch_shape():
    s = _synth_series(size_effect=0.0, seed=3)
    cands = factor_candidates(s, n_perms=30)
    assert {c.cid for c in cands} == {"fac_kr_size_smb", "fac_kr_amihud_illiq", "fac_kr_turnover_neglect"}
    res = cands[0].run()
    assert res is None or ("p" in res and "_spec" in res and "evidence" in res)
