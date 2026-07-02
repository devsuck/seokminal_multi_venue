"""Funding 회계 엔진 테스트 — 부호·성분분리·집계·일별집계·survivorship."""
from __future__ import annotations

import datetime as dt

from research.backtest.funding_backtester import (
    position_pnl, aggregate_positions, aggregate_funding_daily, funding_sum_over, tradable_at,
)
from research.hypotheses.funding_strategies import (
    funding_extreme_reversal, cross_sectional_funding, random_reversal,
)


# ── funding 부호 (제일 중요) ─────────────────────────────────────────────────
def test_funding_sign_long_positive_funding_is_cost():
    # long + 양수 funding → funding_pnl 음수 (long이 지급)
    r = position_pnl(100, 100, "long", 10000, funding_sum=0.01, entry_cost_bps=0, exit_cost_bps=0)
    assert r["funding_pnl"] < 0
    assert abs(r["funding_pnl"] - (-100.0)) < 1e-6  # -1 * 10000 * 0.01


def test_funding_sign_short_positive_funding_is_income():
    r = position_pnl(100, 100, "short", 10000, funding_sum=0.01, entry_cost_bps=0, exit_cost_bps=0)
    assert r["funding_pnl"] > 0
    assert abs(r["funding_pnl"] - 100.0) < 1e-6


def test_funding_sign_negative_flips():
    long_neg = position_pnl(100, 100, "long", 10000, -0.01, 0, 0)
    short_neg = position_pnl(100, 100, "short", 10000, -0.01, 0, 0)
    assert long_neg["funding_pnl"] > 0   # long + 음수펀딩 = 수익
    assert short_neg["funding_pnl"] < 0  # short + 음수펀딩 = 비용


# ── 가격 P&L 방향 ────────────────────────────────────────────────────────────
def test_price_pnl_long_short_directions():
    up_long = position_pnl(100, 110, "long", 10000, 0, 0, 0)
    up_short = position_pnl(100, 110, "short", 10000, 0, 0, 0)
    assert up_long["price_pnl"] > 0 and up_short["price_pnl"] < 0
    assert abs(up_long["price_pnl"] - 1000.0) < 1e-6  # +10% * 10000


def test_cost_reduces_net_and_components_split():
    r = position_pnl(100, 110, "long", 10000, 0.005, 5.0, 5.0)
    # net = price + funding - cost, 성분 분리 확인
    assert abs(r["net"] - (r["price_pnl"] + r["funding_pnl"] - r["trading_cost"])) < 1e-6
    assert r["trading_cost"] > 0


def test_aggregate_splits_components():
    ps = [position_pnl(100, 110, "long", 10000, 0.01, 5, 5),
          position_pnl(100, 90, "short", 10000, 0.01, 5, 5)]
    agg = aggregate_positions(ps)
    assert agg["num_positions"] == 2
    assert abs(agg["net_pnl"] - (agg["price_pnl"] + agg["funding_pnl"] - agg["trading_cost"])) < 1e-4


# ── 일별 funding 집계 ────────────────────────────────────────────────────────
def test_aggregate_funding_daily_sums_per_day():
    base = int(dt.datetime(2025, 3, 3, tzinfo=dt.timezone.utc).timestamp())
    times = [base + h * 3600 for h in range(48)]  # 2일치 시간당
    rates = [0.001] * 48
    daily = aggregate_funding_daily(times, rates)
    assert len(daily) == 2
    for v in daily.values():
        assert abs(v - 0.024) < 1e-9  # 24 * 0.001


def test_funding_sum_over_dates():
    df = {"2025-03-03": 0.02, "2025-03-04": 0.01, "2025-03-05": -0.005}
    assert abs(funding_sum_over(df, ["2025-03-03", "2025-03-04"]) - 0.03) < 1e-9


# ── survivorship: 시점별 tradable ────────────────────────────────────────────
def test_tradable_at_excludes_new_listings():
    # A는 오래됨, B는 신규(이력 부족)
    close = {
        "A": {f"2025-01-{d:02d}": 100.0 for d in range(1, 32)},
        "B": {"2025-01-30": 100.0, "2025-01-31": 101.0},
    }
    uni = tradable_at("2025-01-31", close, min_prior_days=20)
    assert "A" in uni and "B" not in uni  # B는 이력<20일 → 배제


# ── 전략 생성기: synthetic 패널에서 유효 포지션 ───────────────────────────────
def _panel(coin, n=120, funding_fn=None, price_fn=None):
    dates = [f"2025-{(m):02d}-{(d):02d}" for m in range(1, 13) for d in range(1, 11)][:n]
    close = {dt_: (price_fn(i) if price_fn else 100.0 + i) for i, dt_ in enumerate(dates)}
    df = {dt_: (funding_fn(i) if funding_fn else 0.0) for i, dt_ in enumerate(dates)}
    return {"coin": coin, "dates": dates, "close": close, "daily_funding": df}


def test_reversal_generates_positions_on_extreme():
    # 후반부 funding 급등 → z 극단 → short 포지션 발생
    def ff(i):
        return 0.001 if i < 80 else 0.05
    panel = _panel("X", n=120, funding_fn=ff)
    ps = funding_extreme_reversal(panel)
    assert isinstance(ps, list)
    assert any(p["side"] == "short" for p in ps)  # 양수 극단 → 반전 숏


def test_random_reversal_reproducible():
    panel = _panel("X", n=120, funding_fn=lambda i: 0.001 * (i % 5))
    a = random_reversal(panel, 5, hold=3, n_runs=100, seed=7)
    b = random_reversal(panel, 5, hold=3, n_runs=100, seed=7)
    assert a == b and len(a) == 100


def test_cross_sectional_runs():
    panels = {c: _panel(c, n=100, funding_fn=lambda i, k=k: 0.001 * k)
              for k, c in enumerate(["A", "B", "C", "D", "E", "F"])}
    ps = cross_sectional_funding(panels)
    assert isinstance(ps, list)
    # 롱·숏 둘 다 생성(하위 롱/상위 숏)
    if ps:
        assert any(p["side"] == "long" for p in ps) and any(p["side"] == "short" for p in ps)
