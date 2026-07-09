"""오더플로우(풋프린트)/유동성 히트맵 REST+WS. orderflow/manager.py의 OrderflowManager를 소비만 한다.
매매 실행 로직(live_engine 등)과 임포트/상태 공유 없음."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orderflow.manager import default_manager

router = APIRouter()


@router.get("/orderflow/symbols")
def get_orderflow_symbols() -> dict:
    return {"symbols": default_manager.active_symbols()}


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
