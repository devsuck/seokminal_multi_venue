"""OKX 퍼블릭 WS(trades + books 채널) 어댑터 — CVD/대량체결/흡수 지표에 합류시킬
보조 체결 소스이자, COB 유동성 풀에 합류시킬 보조 뎁스 소스.

뎁스는 books5(상위 5단계 풀스냅샷)가 아니라 books 채널(최대 400단계)을 쓴다 — books는
첫 메시지만 action="snapshot"(풀스냅샷)이고 이후는 action="update"(변경분만)라
로컬에서 병합 유지해야 함."""
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent

OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
# 로컬 오더북 유지 상한 — books 채널 자체 최대치(400)까지 다 들고 있는다. 이전엔 200으로
# 잘라서 래더 그룹핑(×100=$10 버킷) 시 스프레드 근처 몇 칸밖에 안 채워지는 문제가 있었음.
LOCAL_BOOK_MAX_LEVELS = 400

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
                "args": [{"channel": "books", "instId": inst_id}],
            }))
            bids: dict[float, float] = {}
            asks: dict[float, float] = {}
            async for raw in connection:
                event = apply_okx_depth_message(raw, coin=coin, bids=bids, asks=asks)
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


def _apply_okx_side(book: dict[float, float], levels: list) -> None:
    """books 채널 레벨: [price, size, "0"(deprecated), numOrders] — size 0은 레벨 제거."""
    for entry in levels:
        p, s = entry[0], entry[1]
        price, size = float(p), float(s)
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size


def apply_okx_depth_message(
    raw: str, coin: str, bids: dict[float, float], asks: dict[float, float]
) -> OrderBookSnapshot | None:
    """books 채널 메시지를 로컬 오더북(bids/asks dict)에 병합 — snapshot이면 초기화 후 채우고,
    update면 변경분만 적용. 호출자가 dict를 스트림 생애주기 동안 들고 있어야 한다."""
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
        if msg.get("action") == "snapshot":
            bids.clear()
            asks.clear()
        _apply_okx_side(bids, book["bids"])
        _apply_okx_side(asks, book["asks"])
        return OrderBookSnapshot(
            symbol=f"{coin}.HL",
            ts=float(book["ts"]) / 1000.0,
            bids=[
                OrderBookLevel(price=p, size=s)
                for p, s in sorted(bids.items(), reverse=True)[:LOCAL_BOOK_MAX_LEVELS]
            ],
            asks=[
                OrderBookLevel(price=p, size=s)
                for p, s in sorted(asks.items())[:LOCAL_BOOK_MAX_LEVELS]
            ],
        )
    except (KeyError, TypeError, ValueError):
        return None
