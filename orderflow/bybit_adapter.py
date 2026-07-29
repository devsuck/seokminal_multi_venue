"""Bybit 퍼블릭 WS v5(publicTrade + orderbook 채널) 어댑터 — CVD/대량체결/흡수 지표에
합류시킬 보조 체결 소스이자, COB 유동성 풀에 합류시킬 보조 뎁스 소스.

뎁스는 스팟 orderbook 채널 중 최대 단계(200)를 쓴다. 첫 메시지만 type="snapshot"(풀스냅샷)이고
이후는 type="delta"(변경분만)라 로컬에서 병합 유지해야 함(OKX books 채널과 동일 패턴)."""
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent

BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/spot"
# 로컬 오더북 유지 상한 — 스팟 orderbook 채널 자체 최대 단계(200)까지 다 들고 있는다.
LOCAL_BOOK_MAX_LEVELS = 200
# orderbook 채널은 변경 있을 때마다 오는데 그대로 매번 정렬+객체화하면 낭비 — 소비자 쪽
# 스로틀(컬렉터 1초/라이브 대시보드 0.15초)이 다 이보다 널널해서 여기서 한 번 더 걸어도
# 아무도 손해 안 봄.
DEPTH_EMIT_THROTTLE_SEC = 0.2

# HL 코인 심볼(예: "BTC") → 바이빗 spot 심볼
BYBIT_SYMBOL_MAP = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}


class BybitOrderflowClient:
    def __init__(
        self,
        base_url: str = BYBIT_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(self, coin: str) -> AsyncIterator[TradeEvent]:
        symbol = BYBIT_SYMBOL_MAP.get(coin)
        if symbol is None:
            return
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({"op": "subscribe", "args": [f"publicTrade.{symbol}"]}))
            async for raw in connection:
                for event in parse_bybit_message(raw, coin=coin):
                    yield event

    async def stream_depth(
        self,
        coin: str,
        *,
        now_fn: Callable[[], float] = time.monotonic,
        throttle_sec: float = DEPTH_EMIT_THROTTLE_SEC,
    ) -> AsyncIterator[OrderBookSnapshot]:
        symbol = BYBIT_SYMBOL_MAP.get(coin)
        if symbol is None:
            return
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({"op": "subscribe", "args": [f"orderbook.200.{symbol}"]}))
            bids: dict[float, float] = {}
            asks: dict[float, float] = {}
            last_emit = float("-inf")
            async for raw in connection:
                # dict 갱신은 매 메시지 하되, 정렬+객체화(비싼 연산)는 스로틀 통과할 때만.
                ts = _merge_bybit_depth_message(raw, bids=bids, asks=asks)
                if ts is None:
                    continue
                now = now_fn()
                if now - last_emit < throttle_sec:
                    continue
                last_emit = now
                yield _materialize_bybit_snapshot(coin, ts, bids, asks)


def parse_bybit_message(raw: str, coin: str) -> list[TradeEvent]:
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
        side_raw = t.get("S")
        if side_raw not in ("Buy", "Sell"):
            continue
        try:
            events.append(TradeEvent(
                symbol=f"{coin}.HL",
                ts=float(t["T"]) / 1000.0,
                price=float(t["p"]),
                size=float(t["v"]),
                side="buy" if side_raw == "Buy" else "sell",
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return events


def _apply_bybit_side(book: dict[float, float], levels: list) -> None:
    """orderbook 채널 레벨: [price, size] — size 0은 레벨 제거."""
    for entry in levels:
        p, s = entry[0], entry[1]
        price, size = float(p), float(s)
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size


def _merge_bybit_depth_message(
    raw: str, bids: dict[float, float], asks: dict[float, float]
) -> float | None:
    """orderbook 채널 메시지를 로컬 오더북(bids/asks dict)에 병합만 하고(정렬/객체화 없음)
    ts만 반환 — snapshot이면 초기화 후 채우고, delta면 변경분만 적용. 호출자가 dict를
    스트림 생애주기 동안 들고 있어야 한다."""
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict):
        return None
    data = msg.get("data")
    if not isinstance(data, dict):
        return None
    try:
        if msg.get("type") == "snapshot":
            bids.clear()
            asks.clear()
        _apply_bybit_side(bids, data["b"])
        _apply_bybit_side(asks, data["a"])
        return float(msg["ts"]) / 1000.0
    except (KeyError, TypeError, ValueError):
        return None


def _materialize_bybit_snapshot(
    coin: str, ts: float, bids: dict[float, float], asks: dict[float, float]
) -> OrderBookSnapshot:
    # model_construct: pydantic 검증(이미 float()로 타입 보장된 값 재검증)이 CPU 낭비 —
    # 값은 그대로, 검증만 스킵.
    return OrderBookSnapshot.model_construct(
        symbol=f"{coin}.HL",
        ts=ts,
        bids=[
            OrderBookLevel.model_construct(price=p, size=s)
            for p, s in sorted(bids.items(), reverse=True)[:LOCAL_BOOK_MAX_LEVELS]
        ],
        asks=[
            OrderBookLevel.model_construct(price=p, size=s)
            for p, s in sorted(asks.items())[:LOCAL_BOOK_MAX_LEVELS]
        ],
    )


def apply_bybit_depth_message(
    raw: str, coin: str, bids: dict[float, float], asks: dict[float, float]
) -> OrderBookSnapshot | None:
    ts = _merge_bybit_depth_message(raw, bids=bids, asks=asks)
    if ts is None:
        return None
    return _materialize_bybit_snapshot(coin, ts, bids, asks)
