"""Binance 퍼블릭 WS(aggTrade + 풀 L2 뎁스) 어댑터 — CVD/대량체결/흡수 지표에
합류시킬 보조 체결 소스이자, COB 유동성 풀에 합류시킬 보조 뎁스 소스.

뎁스는 파티셜 뎁스 스트림(@depth20, 상한 20단계 고정)이 아니라 REST 스냅샷 + diff
스트림 조합으로 로컬 오더북을 유지한다 — 파티셜 스트림은 $0.01 틱 20단계라 폭이
~$0.2뿐이라 래더 그룹핑 배율(×10/×100)을 켜면 전부 한두 칸에 뭉쳐버리는 문제가 있었음."""
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import websockets

from orderflow.models import LiquidationEvent, OrderBookLevel, OrderBookSnapshot, TradeEvent

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
# forceOrder(청산 체결)는 선물 전용 이벤트라 현물 스트림(BINANCE_WS_URL)엔 없음 — USDⓈ-M 선물 WS 별도 접속.
BINANCE_FUTURES_WS_URL = "wss://fstream.binance.com/ws"
BINANCE_REST_URL = "https://api.binance.com/api/v3/depth"
# REST 스냅샷 리밋 최대치(공식 상한 5000) — $0.01 틱이라 스냅샷 자체가 좁은 가격폭만
# 커버하면 래더 그룹핑(×100=$10 버킷)이 몇 칸 안 채워짐, 최대한 넓게 받아온다.
DEPTH_SNAPSHOT_LIMIT = 5000
# 로컬 오더북 유지 상한 — 이전엔 200으로 잘라서 스냅샷+diff로 확보한 폭을 도로 버렸음
# (래더 ×100 배율에서 몇 칸밖에 안 뜨는 원인). ×1000까지 쓰려면 더 넓게 필요해서 스냅샷
# 상한(5000)까지 그대로 들고 있는다. 로컬 dict(bids/asks)는 항상 이만큼 유지하되(diff 병합
# 정확도), 스냅샷으로 객체화할 레벨 수는 stream_depth(max_levels=)로 소비자가 줄일 수 있다 —
# 래더는 5000 다 쓰지만 리서치 컬렉터는 수십 레벨만 쓰는데 매 emit마다 1만 개
# OrderBookLevel을 만들어 버려서 GC가 CPU의 대부분을 먹고 있었음(2026-08-14 프로파일).
LOCAL_BOOK_MAX_LEVELS = 5000
# @depth@100ms(초당 10회) 그대로 매번 정렬+객체화하면 낭비 — 소비자 쪽 스로틀(컬렉터
# 1초/라이브 대시보드 0.15초)이 다 이보다 널널해서 여기서 한 번 더 걸어도 아무도 손해 안 봄.
DEPTH_EMIT_THROTTLE_SEC = 0.2

# HL 코인 심볼(예: "BTC") → 바이낸스 spot 심볼
BINANCE_SYMBOL_MAP = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}


async def _default_fetch_snapshot(pair: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(BINANCE_REST_URL, params={"symbol": pair.upper(), "limit": DEPTH_SNAPSHOT_LIMIT})
        resp.raise_for_status()
        return resp.json()


class BinanceOrderflowClient:
    def __init__(
        self,
        base_url: str = BINANCE_WS_URL,
        futures_base_url: str = BINANCE_FUTURES_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
        fetch_snapshot_fn: Callable[[str], Awaitable[dict]] = _default_fetch_snapshot,
    ) -> None:
        self._base_url = base_url
        self._futures_base_url = futures_base_url
        self._connect_fn = connect_fn
        self._fetch_snapshot_fn = fetch_snapshot_fn

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

    async def stream_depth(
        self,
        coin: str,
        *,
        now_fn: Callable[[], float] = time.monotonic,
        throttle_sec: float = DEPTH_EMIT_THROTTLE_SEC,
        max_levels: int = LOCAL_BOOK_MAX_LEVELS,
    ) -> AsyncIterator[OrderBookSnapshot]:
        pair = BINANCE_SYMBOL_MAP.get(coin)
        if pair is None:
            return

        snapshot = await self._fetch_snapshot_fn(pair)
        last_update_id = snapshot["lastUpdateId"]
        bids: dict[float, float] = {float(p): float(s) for p, s in snapshot["bids"]}
        asks: dict[float, float] = {float(p): float(s) for p, s in snapshot["asks"]}

        url = f"{self._base_url}/{pair}@depth@100ms"
        synced = False
        prev_u: int | None = None
        last_emit = float("-inf")
        async with self._connect_fn(url) as connection:
            async for raw in connection:
                diff = parse_binance_diff_message(raw)
                if diff is None:
                    continue
                if diff["u"] <= last_update_id:
                    continue  # 스냅샷보다 오래된 이벤트 — 폐기.
                if not synced:
                    # 스냅샷 직후 첫 이벤트가 스냅샷 시점을 감싸지 않으면(U > lastUpdateId+1) 갭 —
                    # 최초 1회뿐이라 로그만 남기고 이어감(REST 스냅샷 자체가 이미 최신 상태).
                    if diff["U"] > last_update_id + 1:
                        logging.warning("binance depth stream gap at sync for %s", pair)
                    synced = True
                elif prev_u is not None and diff["U"] != prev_u + 1:
                    # 중간에 갭이 나면 놓친 삭제(size=0) 이벤트 탓에 유령 레벨이 로컬 북에 영구히
                    # 남아 크로스(bid>ask)된 스프레드까지 유발할 수 있음 — REST 스냅샷을 다시 받아
                    # 하드 리싱크. 이번 diff는 새 스냅샷 이후 유효성이 불명확하므로 폐기.
                    logging.warning(
                        "binance depth stream gap for %s: prev_u=%s U=%s, resyncing", pair, prev_u, diff["U"]
                    )
                    snapshot = await self._fetch_snapshot_fn(pair)
                    last_update_id = snapshot["lastUpdateId"]
                    bids.clear()
                    bids.update({float(p): float(s) for p, s in snapshot["bids"]})
                    asks.clear()
                    asks.update({float(p): float(s) for p, s in snapshot["asks"]})
                    synced = False
                    prev_u = None
                    continue
                prev_u = diff["u"]
                apply_binance_diff(bids, diff["b"])
                apply_binance_diff(asks, diff["a"])
                # dict 갱신은 매 메시지 하되, 정렬+객체화(비싼 연산)는 스로틀 통과할 때만 —
                # 100ms 스트림 그대로 매번 5000레벨 재구성하면 대부분 아무도 안 쓰고 버려짐.
                now = now_fn()
                if now - last_emit < throttle_sec:
                    continue
                last_emit = now
                # model_construct: pydantic 검증(이미 float()로 타입 보장된 값 재검증)이
                # CPU 낭비 — 값은 그대로, 검증만 스킵.
                yield OrderBookSnapshot.model_construct(
                    symbol=f"{coin}.HL",
                    ts=time.time(),
                    bids=[
                        OrderBookLevel.model_construct(price=p, size=s)
                        for p, s in sorted(bids.items(), reverse=True)[:max_levels]
                    ],
                    asks=[
                        OrderBookLevel.model_construct(price=p, size=s)
                        for p, s in sorted(asks.items())[:max_levels]
                    ],
                )

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


def apply_binance_diff(book: dict[float, float], updates: list[list[str]]) -> None:
    """diff 이벤트의 한쪽(bids/asks) 배열을 로컬 오더북 dict에 적용 — size 0은 레벨 제거."""
    for p, s in updates:
        price, size = float(p), float(s)
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size


def parse_binance_diff_message(raw: str) -> dict | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("e") != "depthUpdate":
        return None
    try:
        return {"U": int(msg["U"]), "u": int(msg["u"]), "b": msg["b"], "a": msg["a"]}
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
