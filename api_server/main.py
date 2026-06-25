import datetime as dt

from fastapi import FastAPI, HTTPException, Query
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pydantic import BaseModel

from adapters.data_provider import bar_type_for
from backtest_runner.runner import run_backtest

CATALOG_PATH = "./catalog"

app = FastAPI(title="Nautilus Multi-Venue Dashboard API")


def date_to_ns(date_str: str) -> int:
    parsed = dt.date.fromisoformat(date_str)
    event_date = dt.datetime.combine(parsed, dt.time.min, tzinfo=dt.timezone.utc)
    return int(event_date.timestamp() * 1_000_000_000)


class BarOut(BaseModel):
    ts_event: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsResponse(BaseModel):
    instrument_id: str
    bars: list[BarOut]


@app.get("/bars", response_model=BarsResponse)
def get_bars(
    instrument_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
) -> BarsResponse:
    start_ns = date_to_ns(start)
    end_ns = date_to_ns(end)

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    all_bars = catalog.bars(bar_types=[bar_type_str])

    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {instrument_id!r} in range [{start}, {end}]",
        )

    return BarsResponse(
        instrument_id=instrument_id,
        bars=[
            BarOut(
                ts_event=b.ts_event,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in bars
        ],
    )


class BacktestResponse(BaseModel):
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_pnl: float | None
    total_pnl_pct: float | None
    bar_count: int


SUPPORTED_STRATEGIES = {"ema_cross"}


@app.get("/backtest", response_model=BacktestResponse)
def get_backtest(
    instrument_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    strategy: str = Query(...),
    fast: int = Query(10),
    slow: int = Query(20),
    trade_size: int = Query(10),
) -> BacktestResponse:
    if strategy not in SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported strategy {strategy!r}, expected one of {SUPPORTED_STRATEGIES}",
        )

    start_ns = date_to_ns(start)
    end_ns = date_to_ns(end)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    spawn_rules_json = [
        {
            "condition": {"combinator": "AND", "conditions": []},
            "strategy": {
                "class": "backtest_runner.ema_cross_flat:EMACrossFlat",
                "params": {
                    "instrument_id": instrument_id,
                    "bar_type": bar_type_str,
                    "trade_size": trade_size,
                    "fast_ema_period": fast,
                    "slow_ema_period": slow,
                    "request_bars": False,
                    "subscribe_trade_ticks": False,
                },
            },
        }
    ]

    try:
        report = run_backtest(
            instrument_id=instrument_id,
            bar_type_str=bar_type_str,
            start_ns=start_ns,
            end_ns=end_ns,
            catalog_path=CATALOG_PATH,
            spawn_rules_json=spawn_rules_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BacktestResponse(
        sharpe_ratio=report["sharpe_ratio"],
        max_drawdown=report["max_drawdown"],
        total_pnl=report["total_pnl"],
        total_pnl_pct=report["total_pnl_pct"],
        bar_count=report["bar_count"],
    )
