"""베이스라인 — 전략이 운(random)·순진한 규칙(naive)을 이기는지 검정.

핵심: random_same_frequency = 같은 opportunity set / 같은 거래수 / 같은 holding 분포 /
같은 비용으로 N회 랜덤 진입 → net PnL 분포. 전략을 이 분포의 퍼센타일로 판정.
단일 랜덤 1회 비교는 무의미(운) → 반드시 분포."""
from __future__ import annotations

import random as _random

from research.validation.engine import simulate_fixed_hold_longs, simulate_long_short


def random_same_frequency(
    closes: list[float],
    n_trades: int,
    holding_periods: list[int],
    trade_size: float = 10.0,
    cost_bps: float = 0.0,
    eligible_indices: list[int] | None = None,
    n_runs: int = 500,
    seed: int = 42,
) -> list[float]:
    """전략과 동일 조건의 랜덤 롱 진입을 n_runs회 → 각 run의 net total PnL 리스트.

    eligible_indices: 진입 가능 인덱스(ORB면 셋업 가능 시간대만). None=전체 봉.
    holding_periods: 전략의 보유봉수 분포에서 샘플링(같은 holding horizon 유지).
    seed 고정 → 재현성."""
    n = len(closes)
    if eligible_indices is None:
        eligible_indices = list(range(n))
    if n_trades <= 0 or not eligible_indices or not holding_periods:
        return [0.0] * n_runs

    rng = _random.Random(seed)
    results: list[float] = []
    for _ in range(n_runs):
        k = min(n_trades, len(eligible_indices))
        entries = rng.sample(eligible_indices, k) if k < len(eligible_indices) else list(eligible_indices)
        holds = [rng.choice(holding_periods) for _ in entries]
        trades = simulate_fixed_hold_longs(closes, entries, holds, trade_size, cost_bps)
        results.append(round(sum(t["pnl"] for t in trades), 6))
    return results


def naive_buy_hold(
    closes: list[float],
    trade_size: float = 10.0,
    cost_bps: float = 0.0,
) -> dict:
    """순진한 baseline: 첫 봉 매수 → 마지막 봉 청산(항상 롱). 거래 1건 반환."""
    if len(closes) < 2:
        return {"num_trades": 0, "total_pnl": 0.0}
    trades = simulate_long_short(closes, ["BUY"] + ["HOLD"] * (len(closes) - 1), trade_size, cost_bps)
    return {"num_trades": len(trades), "total_pnl": round(sum(t["pnl"] for t in trades), 6)}


def empirical_p_value(strategy_stat: float, random_stats: list[float]) -> dict:
    """몬테카를로 empirical p-value + 퍼센타일.
    p = (1 + #{random >= strategy}) / (N + 1)  (North 2002, +1 스무딩)."""
    n = len(random_stats)
    if n == 0:
        return {"p_value": None, "percentile": None, "n_random": 0,
                "random_beating": None, "random_median": None}
    beating = sum(1 for r in random_stats if r >= strategy_stat)
    below = sum(1 for r in random_stats if r < strategy_stat)
    p_value = (1 + beating) / (n + 1)
    percentile = 100.0 * below / n
    srt = sorted(random_stats)
    median = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0
    return {
        "p_value": round(p_value, 4),
        "percentile": round(percentile, 2),
        "n_random": n,
        "random_beating": beating,
        "random_median": round(median, 6),
    }
