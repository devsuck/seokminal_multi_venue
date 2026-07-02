"""TSMOM 포트폴리오 백테스터 synthetic 테스트."""
from __future__ import annotations

import datetime as dt

from research.backtest.portfolio_backtester import run_portfolio, portfolio_metrics
from research.hypotheses.tsmom import tsmom_weights, buyhold_weights, DEFAULTS


def _trend_panel(sym, n=400, slope=0.002):
    # 추세 + 노이즈(vol targeting 작동하려면 vol>0 필요)
    d0 = dt.date(2020, 1, 1)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]
    close = {}
    px = 100.0
    for i, d in enumerate(dates):
        noise = 0.01 if i % 2 else -0.008  # 진동
        px *= (1 + slope + noise)
        close[d] = px
    return {"symbol": sym, "dates": dates, "close": close}


def test_metrics_sane():
    m = portfolio_metrics([0.001 + (0.0005 if i % 2 else -0.0003) for i in range(300)])
    assert m["ann_return"] > 0 and m["sharpe"] is not None and m["days"] == 300


def test_metrics_underpowered_flag():
    assert portfolio_metrics([0.001] * 100)["underpowered"] is True


def test_tsmom_long_on_uptrend_profits():
    # 꾸준한 상승 → tsmom 롱 → 양수 수익
    panels = {"A": _trend_panel("A", n=500, slope=0.002)}
    r = run_portfolio(panels, tsmom_weights, {}, cost_bps=2.0, rebalance_days=21)
    assert r["metrics"]["days"] > 0
    assert r["metrics"]["total_return"] > 0


def test_tsmom_short_on_downtrend_profits():
    panels = {"A": _trend_panel("A", n=500, slope=-0.002)}
    r = run_portfolio(panels, tsmom_weights, {}, cost_bps=2.0, rebalance_days=21)
    # 하락추세 → tsmom 숏 → 양수(숏이 이익)
    assert r["metrics"]["total_return"] > 0


def test_weights_respect_history_gate():
    # 이력 부족 → weight 없음
    panels = {"A": _trend_panel("A", n=DEFAULTS["lookback"] - 5)}
    w = tsmom_weights(panels, panels["A"]["dates"][-1], {})
    assert w == {} or "A" not in w
