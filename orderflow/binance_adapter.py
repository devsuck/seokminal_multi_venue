"""Binance 퍼블릭 WS(aggTrade + partial depth) 어댑터 — CVD/대량체결/흡수 지표에
합류시킬 보조 체결 소스이자, COB 유동성 풀에 합류시킬 보조 뎁스 소스."""
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import LiquidationEvent, OrderBookLevel, OrderBookSnapshot, TradeEvent

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
# forceOrder(청산 체결)는 선물 전용 이벤트라 현물 스트림(BINANCE_WS_URL)엔 없음 — USDⓈ-M 선물 WS 별도 접속.
BINANCE_FUTURES_WS_URL = "wss://fstream.binance.com/ws"
DEPTH_LEVELS = 20

# HL 코인 심볼(예: "BTC") → 바이낸스 spot 심볼
BINANCE_SYMBOL_MAP = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}


class BinanceOrderflowClient:
    def __init__(
        self,
        base_url: str = BINANCE_WS_URL,
        futures_base_url: str = BINANCE_FUTURES_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._futures_base_url = futures_base_url
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

    async def stream_depth(self, coin: str) -> AsyncIterator[OrderBookSnapshot]:
        pair = BINANCE_SYMBOL_MAP.get(coin)
        if pair is None:
            return
        url = f"{self._base_url}/{pair}@depth{DEPTH_LEVELS}@100ms"
        async with self._connect_fn(url) as connection:
            async for raw in connection:
                event = parse_binance_depth_message(raw, coin=coin)
                if event is not None:
                    yield event

    async def stream_liquidations(self, coin: str) -> AsyncIterator[LiquidationEvent]:
        pair = BINANCE_SYMBOL_MAP.get(coin)
        if pair is None:
            return
        url = f"{self._futures_base_url}/{pair}@forceOrder"
        async with self._connect_fn(url) as connection:
            async for raw in connection:
                event = parse_binance_liquidation_message(raw, coin=coin)
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


def parse_binance_depth_message(
    raw: str, coin: str, now_fn: Callable[[], float] = time.time
) -> OrderBookSnapshot | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or "bids" not in msg or "asks" not in msg:
        return None
    try:
        return OrderBookSnapshot(
            symbol=f"{coin}.HL",
            ts=now_fn(),
            bids=[OrderBookLevel(price=float(p), size=float(s)) for p, s in msg["bids"]],
            asks=[OrderBookLevel(price=float(p), size=float(s)) for p, s in msg["asks"]],
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_binance_liquidation_message(raw: str, coin: str) -> LiquidationEvent | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("e") != "forceOrder":
        return None
    o = msg.get("o")
    if not isinstance(o, dict):
        return None
    try:
        return LiquidationEvent(
            symbol=f"{coin}.HL",
            ts=float(o["T"]) / 1000.0,
            price=float(o.get("ap") or o["p"]),
            size=float(o["q"]),
            # 청산 주문 자체의 방향: 강제 매도(SELL)=롱 청산, 강제 매수(BUY)=숏 청산.
            side="long" if o.get("S") == "SELL" else "short",
        )
    except (KeyError, TypeError, ValueError):
        return None
