"""Deribit 퍼블릭 WS 옵션 체결 어댑터. hl_adapter.py와 동일 패턴(연결+파싱만, 재연결은
options_flow_manager.py가 담당)."""
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import websockets

DERIBIT_WS_URL = "wss://www.deribit.com/ws/api/v2"


@dataclass
class OptionTradeEvent:
    instrument_name: str  # 예: "BTC-27DEC26-100000-C"
    direction: str  # "buy" | "sell"
    price: float  # 옵션 프리미엄(기초자산 단위)
    amount: float  # 계약 수량
    iv: float  # 체결 시점 implied vol (%)
    index_price: float  # 체결 시점 기초자산 지수가
    timestamp: float  # epoch seconds


class DeribitOptionsFlowClient:
    def __init__(
        self,
        currency: str,
        base_url: str = DERIBIT_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self.currency = currency.upper()
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(self) -> AsyncIterator[OptionTradeEvent]:
        channel = f"trades.option.{self.currency}.100ms"
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({
                "jsonrpc": "2.0",
                "method": "public/subscribe",
                "params": {"channels": [channel]},
            }))
            async for raw in connection:
                for event in parse_deribit_trades_message(raw, currency=self.currency):
                    yield event


def parse_deribit_trades_message(raw: str, currency: str) -> list[OptionTradeEvent]:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(msg, dict):
        return []

    params = msg.get("params")
    if not isinstance(params, dict):
        return []

    expected_channel = f"trades.option.{currency.upper()}.100ms"
    if params.get("channel") != expected_channel:
        return []

    data = params.get("data")
    if not isinstance(data, list):
        return []

    try:
        events: list[OptionTradeEvent] = []
        for t in data:
            events.append(OptionTradeEvent(
                instrument_name=t["instrument_name"],
                direction=t["direction"],
                price=float(t["price"]),
                amount=float(t["amount"]),
                iv=float(t.get("iv", 0.0)),
                index_price=float(t.get("index_price", 0.0)),
                timestamp=float(t["timestamp"]) / 1000.0,
            ))
        return events
    except (KeyError, TypeError, ValueError):
        return []
