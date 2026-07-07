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
