import datetime as dt

from fastapi import FastAPI, HTTPException, Query
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pydantic import BaseModel

from adapters.data_provider import bar_type_for

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

    try:
        all_bars = catalog.bars(bar_types=[bar_type_str])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
