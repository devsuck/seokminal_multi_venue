"""HL(오더북+체결) + Binance/OKX(체결만) 통합 스트림.

CVD/대량체결/흡수 지표는 전부 체결 테이프(TradeEvent) 하나로 계산되므로, 세 거래소
체결을 같은 canonical 심볼("{coin}.HL")로 병합해 넘기면 `orderflow/aggregator.py`
이후 파이프라인은 수정 없이 그대로 다중거래소 체결량을 반영한다. HL 단독 대비 표본이
넓어져 대량체결/흡수 판정의 통계적 안정성이 올라간다(개별 거래소 노이즈 희석).

오더북 뎁스(COB 사이드바)는 HL 전용 유지 — Binance/OKX는 체결 이벤트만 공급한다.

거래소별로 독립적으로 재연결한다: 한 소스가 끊겨도 나머지 두 소스는 계속 흐르고,
끊긴 소스만 자체 백오프로 재시도한다(`manager.py`의 심볼 단위 재연결과 별개 계층)."""
import asyncio
import logging
from collections.abc import AsyncIterator, Callable

from orderflow.binance_adapter import BinanceOrderflowClient
from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent
from orderflow.okx_adapter import OkxOrderflowClient

RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0
QUEUE_MAXSIZE = 2000


class MultiVenueOrderflowClient:
    """`stream(coin) -> AsyncIterator[OrderBookSnapshot | TradeEvent]` —
    `orderflow/manager.py`의 `_default_adapter_factory`가 기대하는 것과 동일한 계약."""

    def __init__(
        self,
        hl_client: HyperliquidOrderflowClient | None = None,
        binance_client: BinanceOrderflowClient | None = None,
        okx_client: OkxOrderflowClient | None = None,
    ) -> None:
        self._hl_client = hl_client or HyperliquidOrderflowClient()
        self._binance_client = binance_client or BinanceOrderflowClient()
        self._okx_client = okx_client or OkxOrderflowClient()

    async def stream(self, coin: str) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        pumps = [
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._hl_client.stream(coin), queue, "hyperliquid")),
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._binance_client.stream(coin), queue, "binance")),
            asyncio.ensure_future(_pump_with_reconnect(lambda: self._okx_client.stream(coin), queue, "okx")),
        ]
        try:
            while True:
                yield await queue.get()
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)


async def _pump_with_reconnect(
    make_stream: Callable[[], AsyncIterator], queue: asyncio.Queue, venue: str
) -> None:
    delay = RECONNECT_BASE_DELAY
    while True:
        try:
            async for event in make_stream():
                delay = RECONNECT_BASE_DELAY
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("orderflow sub-stream failed: %s, reconnecting", venue)
        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX_DELAY)
