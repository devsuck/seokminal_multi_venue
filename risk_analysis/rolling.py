import statistics


def rolling_beta(
    instrument_returns: dict[int, float],
    benchmark_returns: dict[int, float],
    window: int = 30,
) -> list[dict]:
    """
    Compute rolling beta and correlation over a sliding window.

    Args:
        instrument_returns: {ts_ns: return} from compute_returns().
        benchmark_returns: {ts_ns: return} for benchmark.
        window: Rolling window size in trading days.

    Returns:
        List of {ts_ns, beta, correlation} sorted by date.
        Only includes points where full window of common dates is available.
    """
    common_dates = sorted(set(instrument_returns.keys()) & set(benchmark_returns.keys()))
    if len(common_dates) < window:
        raise ValueError(
            f"need at least {window} common dates for rolling beta, "
            f"got {len(common_dates)}"
        )

    results = []
    for i in range(window - 1, len(common_dates)):
        window_dates = common_dates[i - window + 1 : i + 1]
        inst = [instrument_returns[d] for d in window_dates]
        bench = [benchmark_returns[d] for d in window_dates]

        try:
            bench_var = statistics.variance(bench)
            if bench_var < 1e-10:
                continue
            beta = statistics.covariance(inst, bench) / bench_var
            corr = statistics.correlation(inst, bench)
        except statistics.StatisticsError:
            continue

        results.append({
            "ts_ns": common_dates[i],
            "beta": beta,
            "correlation": corr,
        })

    return results
