"""오더플로우(풋프린트)/유동성 히트맵 REST+WS. orderflow/manager.py의 OrderflowManager를 소비만 한다.
매매 실행 로직(live_engine 등)과 임포트/상태 공유 없음."""
import gzip
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from orderflow.hl_funding import get_cached_funding
from orderflow.manager import default_manager

router = APIRouter()

# research/run_hl_orderflow_tick_collect.py가 쌓는 DOM 리플레이용 스냅샷 — HL 심볼(BTC.HL 등)만
# 지원, IB 선물은 원시 스냅샷을 저장하지 않는다(orderflow/manager.py와 동일 판단).
_SNAPSHOT_DATA_DIR = Path("research/data/hl_orderbook_snapshot")
_SNAPSHOT_DATE_RE = re.compile(r"^([A-Z]+)_(\d{4}-\d{2}-\d{2})\.jsonl(\.gz)?$")
_HISTORY_SNAPSHOT_DEFAULT_LIMIT = 5000
_HISTORY_SNAPSHOT_MAX_LIMIT = 20000


def _coin_from_hl_symbol(symbol: str) -> str | None:
    if not symbol.endswith(".HL"):
        return None
    coin = symbol[: -len(".HL")]
    return coin or None


def _read_snapshot_file(path: Path):
    opener = path.open if path.suffix != ".gz" else lambda: gzip.open(path, "rt")
    with opener() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


@router.get("/orderflow/symbols")
def get_orderflow_symbols() -> dict:
    return {"symbols": default_manager.active_symbols()}


@router.get("/orderflow/funding/{coin}")
def get_funding(coin: str) -> dict:
    coin = coin.upper()
    cached = get_cached_funding(coin)
    return cached or {
        "coin": coin,
        "funding": 0.0,
        "open_interest": 0.0,
        "mark_px": 0.0,
        "prev_day_px": 0.0,
        "day_ntl_vlm": 0.0,
        "updated_at": 0.0,
    }


@router.get("/orderflow/history/{symbol}/dates")
def get_orderflow_history_dates(symbol: str) -> dict:
    coin = _coin_from_hl_symbol(symbol)
    if coin is None:
        return {"symbol": symbol, "dates": []}
    dates = set()
    if _SNAPSHOT_DATA_DIR.is_dir():
        for path in _SNAPSHOT_DATA_DIR.iterdir():
            m = _SNAPSHOT_DATE_RE.match(path.name)
            if m and m.group(1) == coin:
                dates.add(m.group(2))
    return {"symbol": symbol, "dates": sorted(dates)}


@router.get("/orderflow/history/{symbol}")
def get_orderflow_history(
    symbol: str, date: str, start: float | None = None, end: float | None = None, limit: int = _HISTORY_SNAPSHOT_DEFAULT_LIMIT
) -> dict:
    coin = _coin_from_hl_symbol(symbol)
    if coin is None:
        raise HTTPException(status_code=404, detail=f"no snapshot history for {symbol}")
    limit = min(max(limit, 1), _HISTORY_SNAPSHOT_MAX_LIMIT)

    plain = _SNAPSHOT_DATA_DIR / f"{coin}_{date}.jsonl"
    gz = _SNAPSHOT_DATA_DIR / f"{coin}_{date}.jsonl.gz"
    path = plain if plain.exists() else (gz if gz.exists() else None)
    if path is None:
        return {"symbol": symbol, "date": date, "snapshots": [], "truncated": False}

    snapshots = []
    truncated = False
    for row in _read_snapshot_file(path):
        ts = row["ts"]
        if start is not None and ts < start:
            continue
        if end is not None and ts > end:
            continue
        if len(snapshots) >= limit:
            truncated = True
            break
        snapshots.append(row)
    return {"symbol": symbol, "date": date, "snapshots": snapshots, "truncated": truncated}


@router.websocket("/ws/orderflow/{symbol}")
async def ws_orderflow(websocket: WebSocket, symbol: str) -> None:
    await websocket.accept()
    queue, snapshot = default_manager.subscribe(symbol)
    try:
        await websocket.send_json({"type": "snapshot", "symbol": symbol, **snapshot})
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        default_manager.unsubscribe(symbol, queue)
