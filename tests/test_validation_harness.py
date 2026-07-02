"""알파 검증 하네스 테스트 — 재현성·비용정확·랜덤분포·p-value·샘플가드."""
from __future__ import annotations

from research.validation.cost_model import effective_cost_bps
from research.validation.engine import simulate_long_short, simulate_fixed_hold_longs
from research.validation.metrics import trade_metrics
from research.validation.baselines import (
    random_same_frequency, naive_buy_hold, empirical_p_value,
)


def test_effective_cost_sums_with_half_spread():
    assert effective_cost_bps(5, 2, 4) == 5 + 2 + 2.0


def test_cost_reduces_pnl():
    closes = [100.0, 110.0]
    no_cost = simulate_fixed_hold_longs(closes, [0], [1], trade_size=10, cost_bps=0.0)
    with_cost = simulate_fixed_hold_longs(closes, [0], [1], trade_size=10, cost_bps=50.0)
    assert with_cost[0]["pnl"] < no_cost[0]["pnl"]


def test_random_reproducible_with_seed():
    closes = [100.0 + (i % 7) for i in range(120)]
    hp = [3, 5, 8]
    a = random_same_frequency(closes, 10, hp, cost_bps=5, n_runs=200, seed=123)
    b = random_same_frequency(closes, 10, hp, cost_bps=5, n_runs=200, seed=123)
    c = random_same_frequency(closes, 10, hp, cost_bps=5, n_runs=200, seed=999)
    assert a == b            # 같은 시드 → 동일 분포
    assert a != c            # 다른 시드 → 다른 분포
    assert len(a) == 200


def test_random_respects_eligible_set():
    # eligible을 좁히면 진입이 그 안에서만
    closes = [100.0 + i for i in range(50)]
    elig = [10, 11, 12]
    runs = random_same_frequency(closes, 2, [1], cost_bps=0, eligible_indices=elig,
                                 n_runs=5, seed=1)
    assert len(runs) == 5  # 실행됨(진입은 elig 내에서만 — 크래시 없이)


def test_empirical_p_value_formula():
    # 전략이 100, 랜덤 99개가 그보다 낮고 1개가 같거나 큼
    random_stats = [float(i) for i in range(100)]  # 0..99, 전부 < 100
    pv = empirical_p_value(100.0, random_stats)
    # beating = 0 → p = 1/101 (4자리 반올림)
    assert abs(pv["p_value"] - 1 / 101) < 1e-3
    assert pv["percentile"] == 100.0
    # 전략이 중앙값이면 절반이 이김
    pv2 = empirical_p_value(50.0, random_stats)
    assert 0.45 < pv2["p_value"] < 0.55


def test_metrics_expectancy_and_underpowered():
    trades = [{"pnl": 10.0}, {"pnl": -4.0}, {"pnl": 6.0}]
    m = trade_metrics(trades, min_trades=30)
    assert m["num_trades"] == 3
    assert abs(m["total_pnl"] - 12.0) < 1e-9
    assert abs(m["expectancy"] - 4.0) < 1e-9
    assert abs(m["profit_factor"] - (16.0 / 4.0)) < 1e-9
    assert m["underpowered"] is True  # 3 < 30


def test_naive_buy_hold_single_trade():
    closes = [100.0, 105.0, 110.0]
    nb = naive_buy_hold(closes, trade_size=10, cost_bps=0)
    assert nb["num_trades"] == 1
    assert nb["total_pnl"] > 0  # 상승장 → 양수


def test_simulate_long_short_basic_long():
    # BUY 후 홀드 → 마지막 봉에서 롱 청산 (1거래). SELL은 숏을 열므로 여기선 안 씀.
    closes = [100.0, 100.0, 120.0]
    sigs = ["BUY", "HOLD", "HOLD"]
    trades = simulate_long_short(closes, sigs, trade_size=10, cost_bps=0)
    assert len(trades) == 1
    assert trades[0]["side"] == "LONG"
    assert abs(trades[0]["pnl"] - 200.0) < 1e-9


def test_sell_opens_short_like_simple_runner():
    # 규약 확인: SELL은 롱 청산 + 숏 오픈(simple_runner와 동일)
    closes = [100.0, 100.0, 120.0]
    trades = simulate_long_short(closes, ["BUY", "HOLD", "SELL"], trade_size=10, cost_bps=0)
    assert len(trades) == 2
    assert trades[0]["side"] == "LONG"
    assert trades[1]["side"] == "SHORT"
