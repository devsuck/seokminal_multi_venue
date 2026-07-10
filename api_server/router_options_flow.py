"""Deribit 옵션플로우(체결)+GEX API. orderflow/options_flow_manager.py, orderflow/gex.py를
소비만 한다. 매매 실행 로직과 임포트/상태 공유 없음."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orderflow.gex import get_cached_gex
from orderflow.options_flow_manager import default_manager

router = APIRouter()

SUPPORTED_CURRENCIES = {"BTC", "ETH"}


@router.get("/options-flow/gex/{currency}")
def get_gex(currency: str) -> dict:
    currency = currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        return {"currency": currency, "spot": 0.0, "updated_at": 0.0, "levels": []}
    cached = get_cached_gex(currency)
    return cached or {"currency": currency, "spot": 0.0, "updated_at": 0.0, "levels": []}


@router.websocket("/ws/options-flow/{currency}")
async def ws_options_flow(websocket: WebSocket, currency: str) -> None:
    currency = currency.upper()
    await websocket.accept()
    if currency not in SUPPORTED_CURRENCIES:
        await websocket.close(code=1008)
        return
    queue = default_manager.subscribe(currency)
    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        default_manager.unsubscribe(currency, queue)
