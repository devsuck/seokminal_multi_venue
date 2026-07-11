"""OKX 퍼블릭 WS(trades + books5 채널) 어댑터 — CVD/대량체결/흡수 지표에 합류시킬
보조 체결 소스이자, COB 유동성 풀에 합류시킬 보조 뎁스 소스."""
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent

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

    async def stream_depth(self, coin: str) -> AsyncIterator[OrderBookSnapshot]:
        inst_id = OKX_SYMBOL_MAP.get(coin)
        if inst_id is None:
            return
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({
                "op": "subscribe",
                "args": [{"channel": "books5", "instId": inst_id}],
            }))
            async for raw in connection:
                event = parse_okx_depth_message(raw, coin=coin)
                if event is not None:
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


def parse_okx_depth_message(raw: str, coin: str) -> OrderBookSnapshot | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict):
        return None
    data = msg.get("data")
    if not isinstance(data, list) or not data:
        return None
    book = data[0]
    try:
        return OrderBookSnapshot(
            symbol=f"{coin}.HL",
            ts=float(book["ts"]) / 1000.0,
            # books5 레벨: [price, size, "0"(deprecated), numOrders] — 앞 두 개만 사용.
            bids=[OrderBookLevel(price=float(p), size=float(s)) for p, s, *_ in book["bids"]],
            asks=[OrderBookLevel(price=float(p), size=float(s)) for p, s, *_ in book["asks"]],
        )
    except (KeyError, TypeError, ValueError):
        return None
