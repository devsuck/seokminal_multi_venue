"""심볼별 수집 task 감독 — 재연결 백오프, 예외 흡수(앱 전체에 전파 안 함).
매매 실행 로직(live_engine 등)과 임포트/상태 공유 없음."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from orderflow.aggregator import OrderflowAggregator
from orderflow.ib_adapter import IBOrderflowClient
from orderflow.models import TradeEvent
from orderflow.multi_venue_adapter import MultiVenueOrderflowClient

RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0

TICK_SIZE_BY_SYMBOL = {"BTC.HL": 1.0, "NQ": 0.25}
DEFAULT_TICK_SIZE = 1.0

SUBSCRIBER_QUEUE_MAXSIZE = 1000
BOOK_SNAPSHOT_THROTTLE_SEC = 0.15


def _default_adapter_factory(symbol: str):
    if symbol.endswith(".HL"):
        coin = symbol[: -len(".HL")]
        return MultiVenueOrderflowClient().stream(coin)
    return IBOrderflowClient().stream(symbol)


@dataclass
class _SymbolWorker:
    task: "asyncio.Task"
    aggregator: OrderflowAggregator
    subscribers: set = field(default_factory=set)
    last_book_broadcast_ts: float = 0.0


class OrderflowManager:
    def __init__(self, adapter_factory=None, now_fn: Callable[[], float] = time.time) -> None:
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._now_fn = now_fn
        self._workers: dict[str, _SymbolWorker] = {}

    def active_symbols(self) -> list[str]:
        return list(self._workers.keys())

    def subscribe(self, symbol: str) -> tuple[asyncio.Queue, dict]:
        worker = self._workers.get(symbol)
        if worker is None:
            tick_size = TICK_SIZE_BY_SYMBOL.get(symbol, DEFAULT_TICK_SIZE)
            aggregator = OrderflowAggregator(tick_size=tick_size)
            task = asyncio.ensure_future(self._run(symbol, aggregator))
            worker = _SymbolWorker(task=task, aggregator=aggregator)
            self._workers[symbol] = worker
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAXSIZE)
        worker.subscribers.add(queue)
        return queue, worker.aggregator.snapshot()

    def unsubscribe(self, symbol: str, queue: asyncio.Queue) -> None:
        worker = self._workers.get(symbol)
        if worker is None:
            return
        worker.subscribers.discard(queue)
        if not worker.subscribers:
            worker.task.cancel()
            del self._workers[symbol]

    def _put(self, queue: asyncio.Queue, msg: dict) -> None:
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            queue.put_nowait(msg)

    def _broadcast(self, symbol: str, messages: list[dict]) -> None:
        worker = self._workers.get(symbol)
        if worker is None:
            return
        for queue in worker.subscribers:
            for msg in messages:
                self._put(queue, msg)

    def _broadcast_status(self, symbol: str, state: str) -> None:
        worker = self._workers.get(symbol)
        if worker is None:
            return
        for queue in worker.subscribers:
            self._put(queue, {"type": "status", "state": state})

    async def _run(self, symbol: str, aggregator: OrderflowAggregator) -> None:
        delay = RECONNECT_BASE_DELAY
        was_reconnecting = False
        while True:
            try:
                async for event in self._adapter_factory(symbol):
                    delay = RECONNECT_BASE_DELAY
                    if was_reconnecting:
                        self._broadcast_status(symbol, "live")
                        was_reconnecting = False
                    if isinstance(event, TradeEvent):
                        deltas = [aggregator.on_trade(event)]
                    else:
                        deltas = aggregator.on_book_snapshot(event)
                        worker = self._workers.get(symbol)
                        now = self._now_fn()
                        if worker is not None and now - worker.last_book_broadcast_ts >= BOOK_SNAPSHOT_THROTTLE_SEC:
                            worker.last_book_broadcast_ts = now
                            deltas = [aggregator.latest_book(event), *deltas]
                    self._broadcast(symbol, deltas)
                self._broadcast_status(symbol, "reconnecting")
                was_reconnecting = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("orderflow adapter failed for %s, reconnecting", symbol)
                self._broadcast_status(symbol, "reconnecting")
                was_reconnecting = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)


default_manager = OrderflowManager()
