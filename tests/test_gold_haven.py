"""Gold haven 가설 — 순수 로직 synthetic 테스트 (네트워크 없음)."""
from __future__ import annotations

import datetime as dt

from research.hypotheses.gold_haven import (
    DEFAULTS, gold_haven_weights, buyhold_weights, random_weights,
)


def _price_panel(sym="GC", n=400, slope=0.0005):
    d0 = dt.date(2020, 1, 1)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]
    close = {}
    px = 100.0
    for i, d in enumerate(dates):
        noise = 0.006 if i % 2 else -0.005
        px *= (1 + slope + noise)
        close[d] = px
    return dates, {"symbol": sym, "dates": dates, "close": close}


def _macro_panel(dates, real_rate_vals, vix_vals=None, credit_vals=None):
    vix_vals = vix_vals if vix_vals is not None else [15.0] * len(dates)
    credit_vals = credit_vals if credit_vals is not None else [4.0] * len(dates)
    return {
        "dates": dates,
        "real_rate": dict(zip(dates, real_rate_vals)),
        "vix": dict(zip(dates, vix_vals)),
        "credit_spread": dict(zip(dates, credit_vals)),
    }


def test_gate_bullish_when_real_rate_declining():
    dates, gc = _price_panel()
    # 꾸준히 하락하는 실질금리 (오늘 < lookback일 전)
    real_rate_vals = [5.0 - 0.01 * i for i in range(len(dates))]
    macro = _macro_panel(dates, real_rate_vals)
    params = {**DEFAULTS, "macro": macro}
    d = dates[-1]

    w = gold_haven_weights({"GC": gc}, d, params)
    assert w.get("GC", 0.0) > 0.0


def test_gate_flat_when_real_rate_rising():
    dates, gc = _price_panel()
    # 꾸준히 상승하는 실질금리 → 게이트 FLAT
    real_rate_vals = [1.0 + 0.01 * i for i in range(len(dates))]
    macro = _macro_panel(dates, real_rate_vals)
    params = {**DEFAULTS, "macro": macro}
    d = dates[-1]

    w = gold_haven_weights({"GC": gc}, d, params)
    assert w.get("GC", 0.0) == 0.0


def test_risk_off_boosts_weight_when_gate_bullish():
    dates, gc = _price_panel()
    real_rate_vals = [5.0 - 0.01 * i for i in range(len(dates))]
    # VIX 마지막 값만 스파이크 (나머지는 평온) → z-score 급등 → risk_off
    vix_vals = [15.0] * (len(dates) - 1) + [60.0]
    macro_calm = _macro_panel(dates, real_rate_vals, vix_vals=[15.0] * len(dates))
    macro_stress = _macro_panel(dates, real_rate_vals, vix_vals=vix_vals)
    d = dates[-1]

    w_calm = gold_haven_weights({"GC": gc}, d, {**DEFAULTS, "macro": macro_calm})
    w_stress = gold_haven_weights({"GC": gc}, d, {**DEFAULTS, "macro": macro_stress})
    assert w_stress["GC"] > w_calm["GC"]


def test_risk_off_does_not_trigger_entry_when_gate_flat():
    dates, gc = _price_panel()
    real_rate_vals = [1.0 + 0.01 * i for i in range(len(dates))]  # FLAT 게이트
    vix_vals = [15.0] * (len(dates) - 1) + [60.0]  # risk_off 스파이크
    macro = _macro_panel(dates, real_rate_vals, vix_vals=vix_vals)
    params = {**DEFAULTS, "macro": macro}
    d = dates[-1]

    w = gold_haven_weights({"GC": gc}, d, params)
    assert w.get("GC", 0.0) == 0.0


def test_weight_never_negative():
    dates, gc = _price_panel()
    for real_rate_vals in (
        [5.0 - 0.01 * i for i in range(len(dates))],
        [1.0 + 0.01 * i for i in range(len(dates))],
    ):
        macro = _macro_panel(dates, real_rate_vals)
        params = {**DEFAULTS, "macro": macro}
        w = gold_haven_weights({"GC": gc}, dates[-1], params)
        assert w.get("GC", 0.0) >= 0.0


def test_insufficient_history_returns_no_weight():
    dates, gc = _price_panel(n=DEFAULTS["real_rate_lookback"] - 5)
    real_rate_vals = [5.0 - 0.01 * i for i in range(len(dates))]
    macro = _macro_panel(dates, real_rate_vals)
    params = {**DEFAULTS, "macro": macro}
    w = gold_haven_weights({"GC": gc}, dates[-1], params)
    assert w == {} or "GC" not in w


def test_buyhold_always_long_ignores_macro():
    dates, gc = _price_panel()
    w = buyhold_weights({"GC": gc}, dates[-1], {**DEFAULTS})
    assert w.get("GC", 0.0) > 0.0


def test_random_weights_seeded_reproducible():
    import random
    dates, gc = _price_panel()
    r1 = random.Random(42)
    r2 = random.Random(42)
    w1 = random_weights({"GC": gc}, dates[-1], {**DEFAULTS}, r1)
    w2 = random_weights({"GC": gc}, dates[-1], {**DEFAULTS}, r2)
    assert w1 == w2


import pytest

from research.hypotheses.gold_haven import build_macro_panel


class _FakeFRED:
    """DGS10=일정, CPIAUCSL=월간 완만 상승, VIXCLS/BAMLH0A0HYM2=일정. 실제 API 미호출."""

    def __init__(self, *args, **kwargs):
        pass

    def get_series(self, series_id, start=None, end=None):
        if series_id == "DGS10":
            return [{"date": f"2024-{m:02d}-01", "value": 4.0} for m in range(1, 13)] + \
                   [{"date": f"2024-{m:02d}-15", "value": 4.0} for m in range(1, 13)]
        if series_id == "CPIAUCSL":
            # 2023-01부터 2024-12까지, 매달 0.3씩 증가하는 지수 (YoY 계산용 앞선 1년 포함)
            out = []
            base = 300.0
            months = [(y, m) for y in (2022, 2023, 2024) for m in range(1, 13)]
            for i, (y, m) in enumerate(months):
                out.append({"date": f"{y}-{m:02d}-01", "value": base + 0.3 * i})
            return out
        if series_id == "VIXCLS":
            return [{"date": f"2024-{m:02d}-01", "value": 15.0} for m in range(1, 13)]
        if series_id == "BAMLH0A0HYM2":
            return [{"date": f"2024-{m:02d}-01", "value": 4.0} for m in range(1, 13)]
        raise AssertionError(f"unexpected series_id {series_id}")


def test_build_macro_panel_aligns_to_dates(monkeypatch):
    monkeypatch.setattr("fred.client.FREDClient", _FakeFRED)
    dates = [f"2024-{m:02d}-10" for m in range(1, 13)]

    macro = build_macro_panel(dates)

    assert macro["dates"] == dates
    assert set(macro["real_rate"]) <= set(dates)
    # 매 시점 real_rate 값 존재 (DGS10/CPI YoY 둘 다 forward-fill로 채워짐)
    assert all(d in macro["real_rate"] for d in dates)
    assert all(d in macro["vix"] for d in dates)
    assert all(d in macro["credit_spread"] for d in dates)
    # DGS10=4.0 고정, CPI YoY 대략 12*0.3/base*100 ~ 1.2%대 → real_rate는 4.0보다 약간 작은 양수
    assert 2.0 < macro["real_rate"]["2024-06-10"] < 4.0


def test_build_macro_panel_requires_no_network_beyond_fake(monkeypatch):
    # FREDClient가 몽키패치 안 됐으면 FRED_API_KEY 없어서 KeyError 나야 정상(네트워크 호출 시도 안 함 확인용)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    dates = ["2024-01-10"]
    with pytest.raises(KeyError):
        build_macro_panel(dates)
