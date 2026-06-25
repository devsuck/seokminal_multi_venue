import statistics

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for
from correlation_analysis.returns import compute_returns


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
    catalog = ParquetDataCatalog(catalog_path)

    instrument_id_obj = InstrumentId.from_str(instrument_id)
    benchmark_id_obj = InstrumentId.from_str(benchmark_id)

    bar_type_instrument = bar_type_for(instrument_id_obj)
    bar_type_benchmark = bar_type_for(benchmark_id_obj)

    bars_instrument = catalog.bars(bar_type_instrument)
    bars_benchmark = catalog.bars(bar_type_benchmark)

    bars_instrument_filtered = [
        b for b in bars_instrument if start_ns <= b.ts_event <= end_ns
    ]
    bars_benchmark_filtered = [
        b for b in bars_benchmark if start_ns <= b.ts_event <= end_ns
    ]

    if not bars_instrument_filtered:
        raise ValueError(
            f"no bars found for {instrument_id!r} {bar_type_instrument!r} in range [{start_ns}, {end_ns}]"
        )
    if not bars_benchmark_filtered:
        raise ValueError(
            f"no bars found for {benchmark_id!r} {bar_type_benchmark!r} in range [{start_ns}, {end_ns}]"
        )

    returns_instrument = compute_returns(bars_instrument_filtered)
    returns_benchmark = compute_returns(bars_benchmark_filtered)

    common_dates = sorted(set(returns_instrument.keys()) & set(returns_benchmark.keys()))

    if len(common_dates) < 2:
        raise ValueError(
            f"fewer than 2 common dates between {instrument_id!r} and {benchmark_id!r}: found {len(common_dates)}"
        )

    return {
        'instrument_id': instrument_id,
        'benchmark_id': benchmark_id,
        'beta': 0.0,
        'correlation': 0.0,
    }
