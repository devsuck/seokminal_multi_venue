"""Hyperliquid 퍼블릭 WS(L2Book + trades) 어댑터. 신규 클라이언트 — 기존 hyperliquid/client.py(REST)와 별개.

connect/idle 둘 다 asyncio.wait_for로 감쌈 — macOS 슬립/웨이크 등으로 getaddrinfo가
OS 레벨에서 멈추면(research/net_utils.py 문서화된 것과 동일 클래스 문제) 가드 없이는
이 스트림이 예외도, 로그도 없이 영구 정지한다(2026-08-02, ict-orderflow-paper 프로세스
lsof로 소켓 0개 확인해 실측). wait_for는 블로킹된 OS 스레드 자체는 못 죽이지만(Python
한계, net_utils.py와 동일) 이 태스크는 풀어줘서 재연결 루프가 돌게 한다."""
import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
CONNECT_TIMEOUT_S = 15.0
IDLE_TIMEOUT_S = 30.0  # BTC 체결/호가는 훨씬 촘촘히 옴 — 이 이상 침묵하면 스트림 죽은 것


class HyperliquidOrderflowClient:
    def __init__(
        self,
        base_url: str = HL_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(
        self, coin: str, connect_timeout: float = CONNECT_TIMEOUT_S, idle_timeout: float = IDLE_TIMEOUT_S
    ) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        cm = self._connect_fn(self._base_url)
        connection = await asyncio.wait_for(cm.__aenter__(), connect_timeout)
        try:
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}))
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}))
            aiter = connection.__aiter__()
            while True:
                try:
                    raw = await asyncio.wait_for(aiter.__anext__(), idle_timeout)
                except StopAsyncIteration:
                    return
                for event in parse_hl_message(raw, coin=coin):
                    yield event
        finally:
            await cm.__aexit__(None, None, None)


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
            return [OrderBookSnapshot.model_construct(
                symbol=f"{coin}.HL",
                ts=data["time"] / 1000.0,
                bids=[OrderBookLevel.model_construct(price=float(b["px"]), size=float(b["sz"])) for b in bids_raw],
                asks=[OrderBookLevel.model_construct(price=float(a["px"]), size=float(a["sz"])) for a in asks_raw],
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
