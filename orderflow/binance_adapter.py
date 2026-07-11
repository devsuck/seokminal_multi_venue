"""Binance 퍼블릭 WS(aggTrade) 어댑터 — CVD/대량체결/흡수 지표에 합류시킬 보조 체결
소스. 오더북 뎁스(COB)는 HL 전용 유지 — 여기선 체결 테이프만 공급한다."""
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import TradeEvent

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

# HL 코인 심볼(예: "BTC") → 바이낸스 spot 심볼
BINANCE_SYMBOL_MAP = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}


class BinanceOrderflowClient:
    def __init__(
        self,
        base_url: str = BINANCE_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(self, coin: str) -> AsyncIterator[TradeEvent]:
        pair = BINANCE_SYMBOL_MAP.get(coin)
        if pair is None:
            return
        url = f"{self._base_url}/{pair}@aggTrade"
        async with self._connect_fn(url) as connection:
            async for raw in connection:
                event = parse_binance_message(raw, coin=coin)
                if event is not None:
                    yield event


def parse_binance_message(raw: str, coin: str) -> TradeEvent | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("e") != "aggTrade":
        return None
    try:
        # "m": true면 매수자가 메이커 = 테이커는 매도자 = 공격적 체결 방향은 sell.
        return TradeEvent(
            symbol=f"{coin}.HL",
            ts=msg["T"] / 1000.0,
            price=float(msg["p"]),
            size=float(msg["q"]),
            side="sell" if msg.get("m") else "buy",
        )
    except (KeyError, TypeError, ValueError):
        return None
