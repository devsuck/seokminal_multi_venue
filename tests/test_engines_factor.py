"""KR 횡단면 팩터 엔진 — 합성 데이터로 수학 검증(심은 효과 탐지·무효과≈중앙).

사전등록 7팩터(size·amihud·turnover·PER·PBR·ROIC·F-Score)만. momentum/reversal/sector=기각,
low_vol=WEAK(같은 PIT 데이터로 기검증) → 엔진에 없어야 함(재실험 금지).
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
    assert set(FACTORS) == {
        "kr_size_smb", "kr_amihud_illiq", "kr_turnover_neglect",
        "kr_value_per", "kr_value_pbr", "kr_quality_roic", "kr_quality_fscore",
        "kr_value_quality_composite",
    }
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
    assert {c.cid for c in cands} == {
        "fac_kr_size_smb", "fac_kr_amihud_illiq", "fac_kr_turnover_neglect",
        "fac_kr_value_per", "fac_kr_value_pbr", "fac_kr_quality_roic", "fac_kr_quality_fscore",
        "fac_kr_value_quality_composite",
    }
    res = cands[0].run()
    assert res is None or ("p" in res and "_spec" in res and "evidence" in res)


def _synth_series_value(n_stocks=80, n_days=420, effect=0.0, seed=7):
    """시총 고정(size 신호와 분리) + net_profit만 종목별 차등 → PER 차등. i 클수록 이익 커짐(저PER)."""
    rng = random.Random(seed)
    import datetime as dt
    d0 = dt.date(2024, 1, 2)
    dates = []
    d = d0
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    series, fund = {}, {}
    for i in range(n_stocks):
        net_profit = 1e8 * (1 + i)
        drift = effect * (i / n_stocks)  # 저PER(=i 큼)에 드리프트
        px = 1000.0
        closes, tvals, mcaps = [], [], []
        for _ in dates:
            px *= math.exp(drift + rng.gauss(0, 0.02))
            closes.append(round(px, 2))
            tvals.append(1e8)
            mcaps.append(5e10)  # 전 종목 동일 시총
        code = f"{i:06d}"
        series[code] = {"dates": list(dates), "close": closes, "tval": tvals, "marcap": mcaps}
        fund[code] = {y: {"net_profit": net_profit, "total_equity": net_profit * 10.0}
                      for y in ("2022", "2023", "2024")}
    return series, fund


def test_planted_value_effect_detected():
    s, fund = _synth_series_value(effect=0.004, seed=17)
    r = run_factor("kr_value_per", s, fund=fund, n_perms=120)
    assert r is not None
    assert r["net"] > 0
    assert r["percentile"] >= 90  # 저PER 롱 = 심은 드리프트 방향과 일치


def test_value_signal_none_without_fundamentals():
    s, _ = _synth_series_value(effect=0.0, seed=19)
    assert run_factor("kr_value_per", s, n_perms=50) is None  # fund 없으면 신호 계산 불가


def _synth_series_composite(n_stocks=80, n_days=420, effect=0.0, seed=23):
    """PER/PBR/ROIC/F-Score 4개 필드 전부 채운 fin — composite 경로 전체 행사."""
    rng = random.Random(seed)
    import datetime as dt
    d0 = dt.date(2024, 1, 2)
    dates = []
    d = d0
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    series, fund = {}, {}
    for i in range(n_stocks):
        net_profit = 1e8 * (1 + i)
        total_equity = net_profit * 10.0
        total_assets = total_equity * 2.0
        current_liab = total_assets * 0.3
        current_assets = total_assets * 0.4
        cash = total_assets * 0.1
        op_profit = net_profit * 1.2
        sale = net_profit * 5.0
        gross_profit = sale * 0.4
        op_cashflow = net_profit * 1.1
        total_liab = total_assets - total_equity
        fin = {
            "net_profit": net_profit, "total_equity": total_equity, "sale": sale,
            "total_assets": total_assets, "total_liab": total_liab,
            "current_assets": current_assets, "current_liab": current_liab,
            "cash": cash, "op_profit": op_profit, "op_cashflow": op_cashflow,
            "gross_profit": gross_profit,
            "net_profit_prev": net_profit * 0.9, "total_assets_prev": total_assets * 0.95,
            "total_liab_prev": total_liab * 1.05, "total_equity_prev": total_equity * 0.95,
            "current_assets_prev": current_assets * 0.95, "current_liab_prev": current_liab * 1.02,
            "gross_profit_prev": gross_profit * 0.95, "sale_prev": sale * 0.95,
        }
        drift = effect * (i / n_stocks)  # 저PER/저PBR(=i 큼)에 드리프트 → composite 방향과 일치
        px = 1000.0
        closes, tvals, mcaps = [], [], []
        for _ in dates:
            px *= math.exp(drift + rng.gauss(0, 0.02))
            closes.append(round(px, 2))
            tvals.append(1e8)
            mcaps.append(5e10)
        code = f"{i:06d}"
        series[code] = {"dates": list(dates), "close": closes, "tval": tvals, "marcap": mcaps}
        fund[code] = {y: fin for y in ("2022", "2023", "2024")}
    return series, fund


def test_planted_composite_effect_detected():
    s, fund = _synth_series_composite(effect=0.004, seed=29)
    r = run_factor("kr_value_quality_composite", s, fund=fund, n_perms=120)
    assert r is not None
    assert r["net"] > 0
    assert r["percentile"] >= 90  # 저PER/저PBR 롱 = 심은 드리프트 방향과 일치


def test_composite_signal_none_without_fundamentals():
    s, _ = _synth_series_composite(effect=0.0, seed=31)
    assert run_factor("kr_value_quality_composite", s, n_perms=50) is None
