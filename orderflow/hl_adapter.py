"""Hyperliquid 퍼블릭 WS(L2Book + trades) 어댑터. 신규 클라이언트 — 기존 hyperliquid/client.py(REST)와 별개."""
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"


class HyperliquidOrderflowClient:
    def __init__(
        self,
        base_url: str = HL_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(self, coin: str) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}))
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}))
            async for raw in connection:
                for event in parse_hl_message(raw, coin=coin):
                    yield event


def parse_hl_message(raw: str, coin: str) -> list[OrderBookSnapshot | TradeEvent]:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(msg, dict):
        return []

    channel = msg.get("channel")
    data = msg.get("data")

    if channel == "l2Book" and isinstance(data, dict):
        try:
            levels = data.get("levels") or [[], []]
            bids_raw, asks_raw = levels[0], levels[1]
            return [OrderBookSnapshot(
                symbol=f"{coin}.HL",
                ts=data["time"] / 1000.0,
                bids=[OrderBookLevel(price=float(b["px"]), size=float(b["sz"])) for b in bids_raw],
                asks=[OrderBookLevel(price=float(a["px"]), size=float(a["sz"])) for a in asks_raw],
            )]
        except (KeyError, IndexError, TypeError, ValueError):
            return []

    if channel == "trades" and isinstance(data, list):
        try:
            events: list[OrderBookSnapshot | TradeEvent] = []
            for t in data:
                events.append(TradeEvent(
                    symbol=f"{coin}.HL",
                    ts=t["time"] / 1000.0,
                    price=float(t["px"]),
                    size=float(t["sz"]),
                    side="buy" if t.get("side") == "B" else "sell",
                ))
            return events
        except (KeyError, IndexError, TypeError, ValueError):
            return []

    return []
