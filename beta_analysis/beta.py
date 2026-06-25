def beta_for_pair(
    instrument_id: str,
    benchmark_id: str,
    start_ns: int,
    end_ns: int,
    catalog_path: str,
) -> dict[str, float]:
    """
    Compute market beta and correlation of instrument relative to benchmark.

    Args:
        instrument_id: The asset being analyzed (e.g., "005930.XKRX").
        benchmark_id: The market benchmark (e.g., "KOSPI.XKRX").
        start_ns: Start of analysis window (nanoseconds since epoch).
        end_ns: End of analysis window (nanoseconds since epoch).
        catalog_path: Path to ParquetDataCatalog.

    Returns:
        {
            'instrument_id': str,
            'benchmark_id': str,
            'beta': float,        # Cov(ret_instr, ret_bench) / Var(ret_bench)
            'correlation': float, # Pearson correlation of returns
        }

    Raises:
        ValueError: If instrument/benchmark not found, fewer than 2 common dates,
                    or benchmark has near-zero variance.
    """
    pass
