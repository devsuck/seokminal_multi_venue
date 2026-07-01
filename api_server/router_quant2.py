"""Quant Advanced Routes – Group 2: Pairs Trading & Stress Testing."""
import datetime as dt

import numpy as np

from fastapi import APIRouter, HTTPException, Query
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for
from pairs_trading.johansen import test_cointegration
from stress_testing.scenarios import run_stress_test

CATALOG_PATH = "./catalog"

router = APIRouter(tags=["quant2"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _date_to_ns(date_str: str) -> int:
    parsed = dt.date.fromisoformat(date_str)
    event_date = dt.datetime.combine(parsed, dt.time.min, tzinfo=dt.timezone.utc)
    return int(event_date.timestamp() * 1_000_000_000)


def _ns_to_date(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def _fetch_bars(instrument_id: str, start_ns: int, end_ns: int) -> list:
    """Return filtered bars from the catalog for a given instrument and time range."""
    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    return [b for b in all_bars if start_ns <= b.ts_event <= end_ns]


# ── GET /pairs ────────────────────────────────────────────────────────────────

@router.get("/pairs")
def get_pairs(
    instrument_a: str = Query(..., description="First instrument ID"),
    instrument_b: str = Query(..., description="Second instrument ID"),
    start: dt.date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: dt.date = Query(..., description="End date (YYYY-MM-DD)"),
) -> dict:
    """
    Cointegration / pairs-trading analysis for two instruments.

    Returns Engle-Granger + Johansen test results, hedge ratio, spread,
    z-score series, trading signals, and aligned dates.
    """
    start_ns = _date_to_ns(start.isoformat())
    end_ns = _date_to_ns(end.isoformat())

    bars_a = _fetch_bars(instrument_a, start_ns, end_ns)
    if not bars_a:
        raise HTTPException(
            status_code=400,
            detail=f"No bars found for instrument_a={instrument_a!r} in [{start}, {end}]",
        )

    bars_b = _fetch_bars(instrument_b, start_ns, end_ns)
    if not bars_b:
        raise HTTPException(
            status_code=400,
            detail=f"No bars found for instrument_b={instrument_b!r} in [{start}, {end}]",
        )

    # Build date → close maps
    map_a: dict[str, float] = {_ns_to_date(b.ts_event): float(b.close) for b in bars_a}
    map_b: dict[str, float] = {_ns_to_date(b.ts_event): float(b.close) for b in bars_b}

    # Align: only dates present in both series
    common_dates = sorted(set(map_a.keys()) & set(map_b.keys()))
    if len(common_dates) < 30:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Too few overlapping trading days ({len(common_dates)}) for a reliable "
                "cointegration test. Need at least 30."
            ),
        )

    prices_a = [map_a[d] for d in common_dates]
    prices_b = [map_b[d] for d in common_dates]

    result = test_cointegration(prices_a, prices_b)
    result["dates"] = common_dates
    result["instrument_a"] = instrument_a
    result["instrument_b"] = instrument_b
    result["n_observations"] = len(common_dates)

    return result


# ── GET /stress-test ──────────────────────────────────────────────────────────

@router.get("/stress-test")
def get_stress_test(
    instrument_id: str = Query(..., description="Instrument ID"),
    start: dt.date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: dt.date = Query(..., description="End date (YYYY-MM-DD)"),
    beta: float = Query(1.0, description="Portfolio beta vs. market"),
) -> dict:
    """
    Historical stress test for a single instrument.

    Computes daily returns from close prices, then runs each historical
    scenario (2008 crisis, COVID, etc.) to estimate portfolio impact.
    """
    start_ns = _date_to_ns(start.isoformat())
    end_ns = _date_to_ns(end.isoformat())

    bars = _fetch_bars(instrument_id, start_ns, end_ns)
    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"No bars found for {instrument_id!r} in [{start}, {end}]",
        )

    # Sort by timestamp and compute log returns
    bars_sorted = sorted(bars, key=lambda b: b.ts_event)
    closes = [float(b.close) for b in bars_sorted]

    if len(closes) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 bars to compute returns.",
        )

    closes_arr = np.array(closes)
    returns = np.diff(np.log(closes_arr)).tolist()  # daily log returns

    result = run_stress_test(returns, beta=beta)
    result["instrument_id"] = instrument_id
    result["n_bars"] = len(closes)
    result["period_start"] = start.isoformat()
    result["period_end"] = end.isoformat()

    return result
