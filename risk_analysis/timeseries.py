import math
import statistics


def compute_timeseries(
    returns: dict[int, float],
    benchmark_returns: dict[int, float] | None = None,
    rolling_window: int = 60,
    risk_free_rate: float = 0.0,
) -> list[dict]:
    dates = sorted(returns.keys())
    if not dates:
        return []

    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    cum = 1.0
    peak = 1.0
    bench_cum = 1.0
    bench_dates = set(benchmark_returns.keys()) if benchmark_returns else set()

    points = []
    for i, ts in enumerate(dates):
        r = returns[ts]
        cum *= 1 + r
        peak = max(peak, cum)
        drawdown = (cum / peak) - 1

        rolling_sharpe = None
        if i >= rolling_window - 1:
            window = [returns[dates[j]] for j in range(i - rolling_window + 1, i + 1)]
            excess = [x - daily_rf for x in window]
            mu = statistics.mean(excess)
            sigma = statistics.stdev(excess) if len(excess) > 1 else 0.0
            if sigma > 0:
                rolling_sharpe = mu / sigma * math.sqrt(252)

        bench_cum_val = None
        if benchmark_returns and ts in bench_dates:
            bench_cum *= 1 + benchmark_returns[ts]
            bench_cum_val = bench_cum - 1

        points.append({
            "ts_ns": ts,
            "daily_return": r,
            "cumulative_return": cum - 1,
            "drawdown": drawdown,
            "rolling_sharpe": rolling_sharpe,
            "benchmark_cumulative": bench_cum_val,
        })

    return points
