import statistics

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from correlation_analysis.returns import compute_returns


def corr_matrix(
    instrument_ids: list[str],
    bar_type_strs: list[str],
    start_ns: int,
    end_ns: int,
    catalog_path: str,
) -> dict[tuple[str, str], float]:
    if len(instrument_ids) < 2:
        raise ValueError(
            f"corr_matrix requires at least 2 instruments, got {len(instrument_ids)}"
        )
    if len(instrument_ids) != len(bar_type_strs):
        raise ValueError(
            "instrument_ids and bar_type_strs must be the same length: "
            f"{len(instrument_ids)} != {len(bar_type_strs)}"
        )

    catalog = ParquetDataCatalog(catalog_path)

    returns_by_instrument: dict[str, dict[int, float]] = {}
    for instrument_id, bar_type_str in zip(instrument_ids, bar_type_strs):
        all_bars = catalog.bars(bar_types=[bar_type_str])
        bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
        if not bars:
            raise ValueError(
                f"no bars found for {instrument_id!r} {bar_type_str!r} "
                f"in range [{start_ns}, {end_ns}]"
            )
        returns_by_instrument[instrument_id] = compute_returns(bars)

    common_dates = set(returns_by_instrument[instrument_ids[0]].keys())
    for instrument_id in instrument_ids[1:]:
        common_dates &= set(returns_by_instrument[instrument_id].keys())

    if len(common_dates) < 2:
        raise ValueError(
            f"fewer than 2 dates common to all instruments {instrument_ids}: "
            f"found {len(common_dates)}"
        )

    sorted_dates = sorted(common_dates)
    aligned_returns = {
        instrument_id: [returns_by_instrument[instrument_id][ts] for ts in sorted_dates]
        for instrument_id in instrument_ids
    }

    result: dict[tuple[str, str], float] = {}
    for i, instrument_a in enumerate(instrument_ids):
        for instrument_b in instrument_ids[i:]:
            correlation = statistics.correlation(
                aligned_returns[instrument_a], aligned_returns[instrument_b]
            )
            result[(instrument_a, instrument_b)] = correlation
            result[(instrument_b, instrument_a)] = correlation

    return result
