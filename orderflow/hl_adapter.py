"""Hyperliquid 퍼블릭 WS(L2Book + trades) 어댑터. 신규 클라이언트 — 기존 hyperliquid/client.py(REST)와 별개.

connect/idle 둘 다 asyncio.wait_for로 감쌈 — macOS 슬립/웨이크 등으로 getaddrinfo가
OS 레벨에서 멈추면(research/net_utils.py 문서화된 것과 동일 클래스 문제) 가드 없이는
이 스트림이 예외도, 로그도 없이 영구 정지한다(2026-08-02, ict-orderflow-paper 프로세스
lsof로 소켓 0개 확인해 실측). wait_for는 블로킹된 OS 스레드 자체는 못 죽이지만(Python
한계, net_utils.py와 동일) 이 태스크는 풀어줘서 재연결 루프가 돌게 한다.

⚠️ 위 가드만으로는 안 풀림(2026-08-02 같은 날 추가 실측) — asyncio 자체 resolver
(`loop.getaddrinfo`, 공유 default executor 경유)가 이 프로세스에서 828회 연속
100% 타임아웃 재현됨(재기동해도 동일), 반면 HTF 폴링이 쓰는 순수 스레드 기반
resolver(`research/net_utils.py`)는 같은 호스트로 그 사이 계속 성공 중이었음.
그래서 connect 직전에 `net_utils`로 IP를 직접 resolve해 asyncio resolver를
아예 우회하고, TLS SNI/Host 헤더 보존용으로 `server_hostname`만 원래 호스트로
넘긴다."""
import asyncio
import json
import logging
import socket
from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import urlsplit

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from research.net_utils import call_with_hard_timeout

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
CONNECT_TIMEOUT_S = 15.0
IDLE_TIMEOUT_S = 30.0  # BTC 체결/호가는 훨씬 촘촘히 옴 — 이 이상 침묵하면 스트림 죽은 것
RESOLVE_TIMEOUT_S = 10.0


def resolve_host(host: str) -> str:
    infos = call_with_hard_timeout(
        lambda: socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM),
        RESOLVE_TIMEOUT_S,
    )
    return infos[0][4][0]


class HyperliquidOrderflowClient:
    def __init__(
        self,
        base_url: str = HL_WS_URL,
        connect_fn: Callable[..., Any] = websockets.connect,
        resolve_fn: Callable[[str], str] = resolve_host,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn
        self._resolve_fn = resolve_fn

    async def stream(
        self, coin: str, connect_timeout: float = CONNECT_TIMEOUT_S, idle_timeout: float = IDLE_TIMEOUT_S
    ) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        host = urlsplit(self._base_url).hostname
        logging.info("HL WS: resolving %s", host)
        ip = self._resolve_fn(host)
        logging.info("HL WS: resolved %s -> %s, connecting", host, ip)
        cm = self._connect_fn(self._base_url, host=ip, server_hostname=host)
        connection = await asyncio.wait_for(cm.__aenter__(), connect_timeout)
        logging.info("HL WS: connected")
        try:
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}))
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}))
            aiter = connection.__aiter__()
            msg_count = 0
            while True:
                try:
                    raw = await asyncio.wait_for(aiter.__anext__(), idle_timeout)
                except StopAsyncIteration:
                    return
                msg_count += 1
                if msg_count <= 3 or msg_count % 200 == 0:
                    logging.info("HL WS: msg #%d: %s", msg_count, raw[:200])
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
