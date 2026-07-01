"""Quant Advanced Routes — Group 1.

Endpoints: /cvar, /hurst, /stat-tests, /kelly, /vwap, /monte-carlo-gbm, /regime-hmm
"""
import datetime as dt

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for
from risk_analysis.cvar import compute_cvar
from risk_analysis.hurst import compute_hurst
from risk_analysis.stat_tests import run_stat_tests
from risk_analysis.kelly import compute_kelly
from risk_analysis.vwap import compute_vwap_twap
from monte_carlo.gbm import run_gbm_monte_carlo
from regime_filter.hmm_detector import detect_regime_hmm

router = APIRouter()

CATALOG_PATH = "./catalog"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _date_to_ns(date_str: str) -> int:
    parsed = dt.date.fromisoformat(date_str)
    event_date = dt.datetime.combine(parsed, dt.time.min, tzinfo=dt.timezone.utc)
    return int(event_date.timestamp() * 1_000_000_000)


def _ns_to_date(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def _fetch_bars(instrument_id: str, start: dt.date, end: dt.date) -> list:
    """Return raw bar objects from the Parquet catalog."""
    start_ns = _date_to_ns(start.isoformat())
    end_ns = _date_to_ns(end.isoformat())

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]

    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {instrument_id!r} in range [{start}, {end}]",
        )
    return bars


def _closes(bars: list) -> list[float]:
    return [float(b.close) for b in bars]


def _returns(closes: list[float]) -> list[float]:
    arr = np.array(closes)
    return list(np.diff(arr) / arr[:-1])


def _bars_as_dicts(bars: list) -> list[dict]:
    result = []
    for b in bars:
        result.append(
            {
                "date": _ns_to_date(b.ts_event),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
                "ts_event": b.ts_event,
            }
        )
    return result


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/cvar")
def get_cvar(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    confidence: float = Query(0.95),
) -> dict:
    """CVaR / Expected Shortfall at the requested confidence level (and 0.99)."""
    bars = _fetch_bars(instrument_id, start, end)
    closes = _closes(bars)
    if len(closes) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 bars")
    rets = _returns(closes)

    # Always compute both 95 and 99; make sure the requested level is included
    levels = {0.95, 0.99, confidence}
    result = compute_cvar(rets, confidence_levels=sorted(levels))
    result["instrument_id"] = instrument_id
    result["n_returns"] = len(rets)
    return result


@router.get("/hurst")
def get_hurst(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> dict:
    """Hurst exponent via R/S analysis on closing prices."""
    bars = _fetch_bars(instrument_id, start, end)
    closes = _closes(bars)
    if len(closes) < 20:
        raise HTTPException(status_code=400, detail="need at least 20 bars for Hurst")
    result = compute_hurst(closes)
    result["instrument_id"] = instrument_id
    result["n_prices"] = len(closes)
    return result


@router.get("/stat-tests")
def get_stat_tests(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> dict:
    """ADF stationarity, Ljung-Box autocorrelation, and Jarque-Bera normality tests."""
    bars = _fetch_bars(instrument_id, start, end)
    closes = _closes(bars)
    if len(closes) < 15:
        raise HTTPException(status_code=400, detail="need at least 15 bars")
    rets = _returns(closes)
    result = run_stat_tests(closes, rets)
    result["instrument_id"] = instrument_id
    result["n_returns"] = len(rets)
    return result


@router.get("/kelly")
def get_kelly(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> dict:
    """Kelly Criterion position sizing derived from historical returns."""
    bars = _fetch_bars(instrument_id, start, end)
    closes = _closes(bars)
    if len(closes) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 bars")
    rets = _returns(closes)
    result = compute_kelly(rets)
    result["instrument_id"] = instrument_id
    result["n_returns"] = len(rets)
    return result


@router.get("/vwap")
def get_vwap(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> dict:
    """VWAP and TWAP over the requested date range."""
    bars = _fetch_bars(instrument_id, start, end)
    bar_dicts = _bars_as_dicts(bars)
    result = compute_vwap_twap(bar_dicts)
    result["instrument_id"] = instrument_id
    return result


@router.get("/monte-carlo-gbm")
def get_monte_carlo_gbm(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    horizon_days: int = Query(252, ge=1, le=1260),
    n_simulations: int = Query(1000, ge=100, le=10000),
) -> dict:
    """GBM Monte Carlo price path simulation."""
    bars = _fetch_bars(instrument_id, start, end)
    closes = _closes(bars)
    if len(closes) < 10:
        raise HTTPException(status_code=400, detail="need at least 10 bars")
    rets = _returns(closes)
    result = run_gbm_monte_carlo(rets, horizon_days=horizon_days, n_simulations=n_simulations)
    result["instrument_id"] = instrument_id
    result["training_bars"] = len(bars)
    return result


@router.get("/regime-hmm")
def get_regime_hmm(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    n_components: int = Query(2, ge=2, le=3),
) -> dict:
    """HMM-based market regime detection."""
    bars = _fetch_bars(instrument_id, start, end)
    closes = _closes(bars)
    if len(closes) < 30:
        raise HTTPException(status_code=400, detail="need at least 30 bars for HMM")
    rets = _returns(closes)

    hmm_result = detect_regime_hmm(rets, n_components=n_components)

    # Build per-bar regime time series
    # We re-run prediction to get individual state labels
    # (detect_regime_hmm returns aggregate info; we need per-bar labels too)
    import numpy as _np
    from hmmlearn import hmm as _hmm

    _ret_arr = _np.array(rets).reshape(-1, 1)
    _model = _hmm.GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    _model.fit(_ret_arr)
    _hidden = _model.predict(_ret_arr)

    _state_means = [_model.means_[i, 0] for i in range(n_components)]
    _state_order = _np.argsort(_state_means)
    _mean_vol = float(_np.mean([_np.sqrt(_model.covars_[s, 0, 0]) for s in range(n_components)]))
    _regime_names: dict[int, str] = {}
    for rank, state in enumerate(_state_order):
        vol = float(_np.sqrt(_model.covars_[state, 0, 0]))
        if rank == len(_state_order) - 1:
            _regime_names[state] = "bull_low_vol" if vol < _mean_vol else "bull_high_vol"
        else:
            _regime_names[state] = "bear_high_vol" if vol > _mean_vol else "bear_low_vol"

    # bars[0] is the first price; returns start from bars[1] (diff of closes)
    regime_series = []
    for i, state in enumerate(_hidden):
        bar = bars[i + 1]  # align: return[i] = close[i+1]/close[i] - 1
        regime_series.append(
            {
                "date": _ns_to_date(bar.ts_event),
                "regime": _regime_names[int(state)],
                "state_index": int(state),
            }
        )

    hmm_result["instrument_id"] = instrument_id
    hmm_result["regime_series"] = regime_series
    return hmm_result
