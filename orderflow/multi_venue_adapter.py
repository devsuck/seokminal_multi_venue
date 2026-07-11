"""HL + Binance + OKX 통합 스트림 — 체결 테이프 병합 + 오더북 유동성 풀링.

CVD/대량체결/흡수 지표는 전부 체결 테이프(TradeEvent) 하나로 계산되므로, 세 거래소
체결을 같은 canonical 심볼("{coin}.HL")로 병합해 넘기면 `orderflow/aggregator.py`
이후 파이프라인은 수정 없이 그대로 다중거래소 체결량을 반영한다. HL 단독 대비 표본이
넓어져 대량체결/흡수 판정의 통계적 안정성이 올라간다(개별 거래소 노이즈 희석).

오더북 뎁스(COB)도 세 거래소를 "유동성 풀"로 합친다: 거래소별 최신 스냅샷을 들고
있다가, 어느 한 곳이 갱신될 때마다 가격을 tick_size 단위로 반올림해 같은 가격대의
잔량(size)을 합산한 풀링 스냅샷 하나를 내보낸다. 거래소마다 절대가가 미세하게 달라
틱 반올림 없이는 합산이 무의미해진다. Binance/OKX는 각각 파티셜 뎁스(top 20)/books5
(top 5)라 HL 원장보다 얕지만, 풀은 "부가 유동성 정보"지 HL 원장을 대체하는 게
아니므로 얕아도 무방하다.

거래소별로 독립적으로 재연결한다: 한 소스가 끊겨도 나머지는 계속 흐르고, 끊긴
소스만 자체 백오프로 재시도한다(`manager.py`의 심볼 단위 재연결과 별개 계층). 뎁스
풀은 살아있는 소스의 최신 스냅샷만으로 계산되므로, 소스 하나가 끊기면 그 소스의
마지막 스냅샷이 다음 갱신 전까지 정체된 채로 풀에 남는다(오래된 잔량이 섞이는 대신
싱크 자체가 끊기진 않는다)."""
import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Callable, Iterable

from orderflow.binance_adapter import BinanceOrderflowClient
from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from orderflow.okx_adapter import OkxOrderflowClient

RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0
QUEUE_MAXSIZE = 2000
POOL_DEPTH_LEVELS = 25


class MultiVenueOrderflowClient:
    """`stream(coin) -> AsyncIterator[OrderBookSnapshot | TradeEvent]` —
    `orderflow/manager.py`의 `_default_adapter_factory`가 기대하는 것과 동일한 계약."""

    def __init__(
        self,
        hl_client: HyperliquidOrderflowClient | None = None,
        binance_client: BinanceOrderflowClient | None = None,
        okx_client: OkxOrderflowClient | None = None,
        tick_size: float = 1.0,
    ) -> None:
        self._hl_client = hl_client or HyperliquidOrderflowClient()
        self._binance_client = binance_client or BinanceOrderflowClient()
        self._okx_client = okx_client or OkxOrderflowClient()
        self._tick_size = tick_size

    async def stream(self, coin: str) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        latest_books: dict[str, OrderBookSnapshot] = {}
        sink = _make_pooling_sink(coin, queue, latest_books, self._tick_size)

        pumps = [
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._hl_client.stream(coin), sink, "hyperliquid")),
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._binance_client.stream(coin), sink, "binance-trades")),
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._binance_client.stream_depth(coin), sink, "binance-depth")),
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._okx_client.stream(coin), sink, "okx-trades")),
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._okx_client.stream_depth(coin), sink, "okx-depth")),
        ]
        try:
            while True:
                yield await queue.get()
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)


def _make_pooling_sink(
    coin: str,
    queue: asyncio.Queue,
    latest_books: dict[str, OrderBookSnapshot],
    tick_size: float,
) -> Callable[[OrderBookSnapshot | TradeEvent, str], "asyncio.Future"]:
    async def sink(event: OrderBookSnapshot | TradeEvent, venue: str) -> None:
        if isinstance(event, OrderBookSnapshot):
            latest_books[venue] = event
            await queue.put(_pool_books(coin, latest_books, tick_size))
        else:
            await queue.put(event)

    return sink


def _round_to_tick(price: float, tick_size: float) -> float:
    return round(math.floor(price / tick_size + 1e-9) * tick_size, 8)


def _pool_levels(
    levels_by_venue: Iterable[list[OrderBookLevel]], tick_size: float, reverse: bool
) -> list[OrderBookLevel]:
    pooled: dict[float, float] = {}
    for levels in levels_by_venue:
        for lvl in levels:
            key = _round_to_tick(lvl.price, tick_size)
            pooled[key] = pooled.get(key, 0.0) + lvl.size
    ordered = sorted(pooled.items(), key=lambda kv: kv[0], reverse=reverse)
    return [OrderBookLevel(price=p, size=s) for p, s in ordered[:POOL_DEPTH_LEVELS]]


def _pool_books(coin: str, latest_books: dict[str, OrderBookSnapshot], tick_size: float) -> OrderBookSnapshot:
    bids = _pool_levels((b.bids for b in latest_books.values()), tick_size, reverse=True)
    asks = _pool_levels((b.asks for b in latest_books.values()), tick_size, reverse=False)
    ts = max((b.ts for b in latest_books.values()), default=time.time())
    return OrderBookSnapshot(symbol=f"{coin}.HL", ts=ts, bids=bids, asks=asks)


async def _pump_with_reconnect(
    make_stream: Callable[[], AsyncIterator],
    sink: Callable[[OrderBookSnapshot | TradeEvent, str], "asyncio.Future"],
    venue: str,
) -> None:
    delay = RECONNECT_BASE_DELAY
    while True:
        try:
            async for event in make_stream():
                delay = RECONNECT_BASE_DELAY
                await sink(event, venue)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("orderflow sub-stream failed: %s, reconnecting", venue)
        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX_DELAY)
