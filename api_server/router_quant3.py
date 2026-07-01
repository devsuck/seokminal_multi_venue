"""Quant Advanced Routes (Group 3): Risk Parity, Black-Litterman, Factor Attribution."""
import datetime as dt
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for
from portfolio_advanced.risk_parity import compute_risk_parity
from portfolio_advanced.black_litterman import compute_black_litterman
from portfolio_advanced.fama_french import compute_factor_attribution

CATALOG_PATH = "./catalog"

router = APIRouter(tags=["quant-advanced"])


# ── Helpers ─────────────────────────────────────────────────────────────────

def _date_to_ns(date_str: str) -> int:
    parsed = dt.date.fromisoformat(date_str)
    event_date = dt.datetime.combine(parsed, dt.time.min, tzinfo=dt.timezone.utc)
    return int(event_date.timestamp() * 1_000_000_000)


def _ts_to_date(ts_ns: int) -> str:
    return datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%d")


def _fetch_bars(instrument_id: str, start: str, end: str) -> list:
    """Fetch bars for an instrument within [start, end] date range."""
    start_ns = _date_to_ns(start)
    end_ns = _date_to_ns(end)
    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    return [b for b in all_bars if start_ns <= b.ts_event <= end_ns]


def _bars_to_price_series(bars: list) -> dict[str, float]:
    """Convert bars to {date_str: close_price} mapping."""
    result: dict[str, float] = {}
    for b in bars:
        date = _ts_to_date(b.ts_event)
        result[date] = float(b.close)
    return result


def _compute_returns_from_prices(prices: dict[str, float]) -> tuple[list[str], list[float]]:
    """Compute daily returns from a date->price dict. Returns (dates, returns)."""
    sorted_dates = sorted(prices.keys())
    dates = []
    returns = []
    for i in range(1, len(sorted_dates)):
        prev = prices[sorted_dates[i - 1]]
        curr = prices[sorted_dates[i]]
        if prev != 0:
            dates.append(sorted_dates[i])
            returns.append((curr - prev) / prev)
    return dates, returns


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/risk-parity")
def get_risk_parity(
    instrument_ids: str = Query(..., description="Comma-separated instrument IDs, e.g. AAPL.NASDAQ,MSFT.NASDAQ"),
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
) -> dict:
    """
    Risk parity portfolio: each asset contributes equally to total portfolio risk.
    """
    ids = [iid.strip() for iid in instrument_ids.split(",") if iid.strip()]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 instrument_ids required")

    # Fetch price series for each instrument
    price_series: dict[str, dict[str, float]] = {}
    for iid in ids:
        bars = _fetch_bars(iid, start, end)
        if not bars:
            raise HTTPException(status_code=400, detail=f"No bars found for {iid!r} in [{start}, {end}]")
        price_series[iid] = _bars_to_price_series(bars)

    # Find common dates across all instruments (using return dates, which are offset by 1)
    # First compute returns per instrument, then intersect dates
    returns_by_inst: dict[str, dict[str, float]] = {}
    for iid in ids:
        dates, rets = _compute_returns_from_prices(price_series[iid])
        returns_by_inst[iid] = dict(zip(dates, rets))

    common_dates = sorted(
        set.intersection(*[set(r.keys()) for r in returns_by_inst.values()])
    )
    if len(common_dates) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient common data: only {len(common_dates)} overlapping return dates (need ≥30)",
        )

    # Build returns matrix (T x N)
    returns_matrix = np.array(
        [[returns_by_inst[iid][d] for iid in ids] for d in common_dates],
        dtype=float,
    )

    result = compute_risk_parity(returns_matrix, ids)
    result["instrument_ids"] = ids
    result["common_dates"] = len(common_dates)
    result["start"] = common_dates[0]
    result["end"] = common_dates[-1]
    return result


# ── Black-Litterman ──────────────────────────────────────────────────────────

class ViewItem(BaseModel):
    instrument: str
    expected_return: float
    confidence: float = 0.5


class BlackLittermanRequest(BaseModel):
    instrument_ids: list[str]
    start: str
    end: str
    views: list[ViewItem] = []
    tau: float = 0.05
    risk_aversion: float = 2.5


@router.post("/black-litterman")
def post_black_litterman(req: BlackLittermanRequest) -> dict:
    """
    Black-Litterman portfolio optimization with optional investor views.
    """
    ids = req.instrument_ids
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 instrument_ids required")

    # Fetch and align
    price_series: dict[str, dict[str, float]] = {}
    for iid in ids:
        bars = _fetch_bars(iid, req.start, req.end)
        if not bars:
            raise HTTPException(status_code=400, detail=f"No bars found for {iid!r} in [{req.start}, {req.end}]")
        price_series[iid] = _bars_to_price_series(bars)

    returns_by_inst: dict[str, dict[str, float]] = {}
    for iid in ids:
        dates, rets = _compute_returns_from_prices(price_series[iid])
        returns_by_inst[iid] = dict(zip(dates, rets))

    common_dates = sorted(
        set.intersection(*[set(r.keys()) for r in returns_by_inst.values()])
    )
    if len(common_dates) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient common data: only {len(common_dates)} overlapping return dates (need ≥30)",
        )

    returns_matrix = np.array(
        [[returns_by_inst[iid][d] for iid in ids] for d in common_dates],
        dtype=float,
    )

    views_dicts = [v.model_dump() for v in req.views]

    result = compute_black_litterman(
        returns_matrix=returns_matrix,
        instrument_ids=ids,
        views=views_dicts,
        tau=req.tau,
        risk_aversion=req.risk_aversion,
    )
    result["instrument_ids"] = ids
    result["common_dates"] = len(common_dates)
    result["start"] = common_dates[0]
    result["end"] = common_dates[-1]
    return result


# ── Factor Attribution ───────────────────────────────────────────────────────

@router.get("/factor-attribution")
def get_factor_attribution(
    instrument_id: str = Query(..., description="Single instrument ID"),
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
) -> dict:
    """
    Fama-French 3-factor attribution for a single instrument.
    Downloads FF3 daily factors and runs OLS regression.
    """
    bars = _fetch_bars(instrument_id, start, end)
    if not bars:
        raise HTTPException(status_code=400, detail=f"No bars found for {instrument_id!r} in [{start}, {end}]")

    prices = _bars_to_price_series(bars)
    dates, returns = _compute_returns_from_prices(prices)

    if len(dates) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data: only {len(dates)} return observations (need ≥30)",
        )

    result = compute_factor_attribution(
        dates=dates,
        returns=returns,
        start=start,
        end=end,
    )
    result["instrument_id"] = instrument_id
    result["total_return_obs"] = len(dates)
    return result
