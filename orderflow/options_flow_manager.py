"""Deribit 옵션 체결 스트림 매니저 — orderflow/manager.py(OrderflowManager)의 재연결
백오프/큐 브로드캐스트 구조를 옵션 체결(집계 없음, 원본 그대로 전달)용으로 경량화한 버전."""
import asyncio
import logging
from dataclasses import dataclass, field

from orderflow.deribit_adapter import DeribitOptionsFlowClient, OptionTradeEvent

RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0
SUBSCRIBER_QUEUE_MAXSIZE = 1000


def _default_adapter_factory(currency: str):
    return DeribitOptionsFlowClient(currency).stream()


@dataclass
class _CurrencyWorker:
    task: "asyncio.Task"
    subscribers: set = field(default_factory=set)


class OptionsFlowManager:
    def __init__(self, adapter_factory=None) -> None:
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._workers: dict[str, _CurrencyWorker] = {}

    def active_currencies(self) -> list[str]:
        return list(self._workers.keys())

    def subscribe(self, currency: str) -> asyncio.Queue:
        currency = currency.upper()
        worker = self._workers.get(currency)
        if worker is None:
            task = asyncio.ensure_future(self._run(currency))
            worker = _CurrencyWorker(task=task)
            self._workers[currency] = worker
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAXSIZE)
        worker.subscribers.add(queue)
        return queue

    def unsubscribe(self, currency: str, queue: asyncio.Queue) -> None:
        currency = currency.upper()
        worker = self._workers.get(currency)
        if worker is None:
            return
        worker.subscribers.discard(queue)
        if not worker.subscribers:
            worker.task.cancel()
            del self._workers[currency]

    def _put(self, queue: asyncio.Queue, msg: dict) -> None:
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            queue.put_nowait(msg)

    def _broadcast(self, currency: str, msg: dict) -> None:
        worker = self._workers.get(currency)
        if worker is None:
            return
        for queue in worker.subscribers:
            self._put(queue, msg)

    def _broadcast_status(self, currency: str, state: str) -> None:
        self._broadcast(currency, {"type": "status", "state": state})

    async def _run(self, currency: str) -> None:
        delay = RECONNECT_BASE_DELAY
        was_reconnecting = False
        while True:
            try:
                async for event in self._adapter_factory(currency):
                    delay = RECONNECT_BASE_DELAY
                    if was_reconnecting:
                        self._broadcast_status(currency, "live")
                        was_reconnecting = False
                    self._broadcast(currency, _event_to_msg(event))
                self._broadcast_status(currency, "reconnecting")
                was_reconnecting = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("options-flow adapter failed for %s, reconnecting", currency)
                self._broadcast_status(currency, "reconnecting")
                was_reconnecting = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)


def _event_to_msg(event: OptionTradeEvent) -> dict:
    return {
        "type": "trade",
        "instrument_name": event.instrument_name,
        "direction": event.direction,
        "price": event.price,
        "amount": event.amount,
        "iv": event.iv,
        "index_price": event.index_price,
        "timestamp": event.timestamp,
    }


default_manager = OptionsFlowManager()
