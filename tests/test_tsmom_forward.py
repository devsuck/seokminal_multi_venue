"""TSMOM forward-test 모듈 테스트 (동결 config + 리포트 유틸)."""
from __future__ import annotations

import datetime as dt

from research.paper import tsmom_config as CFG
from research.paper.tsmom_forward import trend_regime_score, monthly_returns


def _panel(sym, n=400, slope=0.003):
    d0 = dt.date(2022, 1, 1)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]
    px = 100.0; close = {}
    for i, d in enumerate(dates):
        px *= (1 + slope + (0.01 if i % 2 else -0.008))
        close[d] = px
    return {"symbol": sym, "dates": dates, "close": close}


def test_config_frozen_constants():
    assert len(CFG.UNIVERSE) == 32
    assert CFG.PARAMS["lookback"] == 252 and CFG.REBALANCE_DAYS == 21
    assert CFG.STATUS == "paper_candidate_forward_test_required"


def test_monthly_returns_groups_by_month():
    daily = [0.01, 0.02, -0.01, 0.03]
    dates = ["2025-01-05", "2025-01-20", "2025-02-03", "2025-02-15"]
    m = monthly_returns(daily, dates)
    assert set(m.keys()) == {"2025-01", "2025-02"}


def test_trend_regime_score_strong_trend_high():
    pn = {"A": _panel("A", n=400, slope=0.004), "B": _panel("B", n=400, slope=0.004)}
    r = trend_regime_score(pn)  # 강한 추세 → score 큼
    assert r["n"] == 2 and r["regime_score"] > 0.5


def test_trend_regime_score_handles_short_history():
    pn = {"A": _panel("A", n=100)}  # 이력 부족
    r = trend_regime_score(pn)
    assert r["n"] == 0 and r["regime_score"] is None
