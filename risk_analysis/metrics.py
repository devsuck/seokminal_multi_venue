import math
import statistics


PERIODS_PER_YEAR = 252


def compute_risk_metrics(
    returns: list[float],
    benchmark_returns: list[float] | None = None,
    risk_free_rate: float = 0.0,
) -> dict[str, float | None]:
    """
    Compute risk/performance metrics from a list of daily returns.

    Args:
        returns: Daily returns for the instrument (decimals, e.g. 0.01 = 1%).
        benchmark_returns: Aligned daily returns for the benchmark (same length).
        risk_free_rate: Annual risk-free rate (decimal). Default 0.

    Returns dict with keys:
        sharpe_ratio, sortino_ratio, volatility, max_drawdown,
        var_95, calmar_ratio, alpha, r_squared
    """
    if len(returns) < 2:
        raise ValueError(f"need at least 2 return observations, got {len(returns)}")

    daily_rf = risk_free_rate / PERIODS_PER_YEAR
    excess = [r - daily_rf for r in returns]

    mean_excess = statistics.mean(excess)
    vol = statistics.stdev(returns)
    ann_vol = vol * math.sqrt(PERIODS_PER_YEAR)
    ann_return = (math.prod(1 + r for r in returns) ** (PERIODS_PER_YEAR / len(returns))) - 1

    # Sharpe
    sharpe = (mean_excess / vol * math.sqrt(PERIODS_PER_YEAR)) if vol > 1e-10 else None

    # Sortino — downside deviation only
    downside = [r for r in excess if r < 0]
    if len(downside) >= 2:
        downside_std = statistics.stdev(downside)
        sortino = (mean_excess / downside_std * math.sqrt(PERIODS_PER_YEAR)) if downside_std > 1e-10 else None
    else:
        sortino = None

    # Max Drawdown
    peak = 1.0
    equity = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak
        if dd > max_dd:
            max_dd = dd

    # VaR 95% (historical, 1-day)
    sorted_returns = sorted(returns)
    var_idx = max(0, int(len(sorted_returns) * 0.05) - 1)
    var_95 = -sorted_returns[var_idx]

    # Calmar
    calmar = (ann_return / max_dd) if max_dd > 1e-10 else None

    # Alpha + R² vs benchmark
    alpha: float | None = None
    r_squared: float | None = None
    if benchmark_returns is not None and len(benchmark_returns) == len(returns):
        try:
            bench_var = statistics.variance(benchmark_returns)
            if bench_var > 1e-10:
                beta = statistics.covariance(returns, benchmark_returns) / bench_var
                bench_mean = statistics.mean(benchmark_returns)
                alpha = ann_return - (risk_free_rate + beta * (bench_mean * PERIODS_PER_YEAR - risk_free_rate))
                corr = statistics.correlation(returns, benchmark_returns)
                r_squared = corr ** 2
        except statistics.StatisticsError:
            pass

    return {
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "volatility": ann_vol,
        "max_drawdown": max_dd,
        "var_95": var_95,
        "calmar_ratio": calmar,
        "alpha": alpha,
        "r_squared": r_squared,
        "annualized_return": ann_return,
        "observation_count": len(returns),
    }
