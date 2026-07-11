"""OKX 퍼블릭 WS(trades 채널) 어댑터 — CVD/대량체결/흡수 지표에 합류시킬 보조 체결
소스. 오더북 뎁스(COB)는 HL 전용 유지 — 여기선 체결 테이프만 공급한다."""
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import TradeEvent

OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

# HL 코인 심볼(예: "BTC") → OKX instId
OKX_SYMBOL_MAP = {"BTC": "BTC-USDT", "ETH": "ETH-USDT", "SOL": "SOL-USDT"}


class OkxOrderflowClient:
    def __init__(
        self,
        base_url: str = OKX_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(self, coin: str) -> AsyncIterator[TradeEvent]:
        inst_id = OKX_SYMBOL_MAP.get(coin)
        if inst_id is None:
            return
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({
                "op": "subscribe",
                "args": [{"channel": "trades", "instId": inst_id}],
            }))
            async for raw in connection:
                for event in parse_okx_message(raw, coin=coin):
                    yield event


def parse_okx_message(raw: str, coin: str) -> list[TradeEvent]:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(msg, dict):
        return []
    data = msg.get("data")
    if not isinstance(data, list):
        return []

    events: list[TradeEvent] = []
    for t in data:
        side = t.get("side")
        if side not in ("buy", "sell"):
            continue
        try:
            events.append(TradeEvent(
                symbol=f"{coin}.HL",
                ts=float(t["ts"]) / 1000.0,
                price=float(t["px"]),
                size=float(t["sz"]),
                side=side,
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return events
