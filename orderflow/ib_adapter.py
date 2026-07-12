"""IBKR 심볼별 지속 연결 어댑터 — reqMktDepth + reqTickByTickData(Last, BidAsk) 동시 구독.
기존 backends/ib/client.py의 IBClient(호출 단위 연결)는 건드리지 않는다 — 이건 별도 클래스."""
import asyncio
import datetime as dt
import os
from collections.abc import AsyncIterator

from ib_async import IB
from ib_async.contract import Contract, Future, Stock

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from orderflow.tick_rule import classify

DEPTH_ROWS = 10
_FUTURES_SYMBOLS = {"NQ": "CME", "ES": "CME", "GC": "COMEX"}


class IBOrderflowClient:
    def __init__(
        self,
        host: str | None = None,
        port: int = 7497,
        client_id: int | None = None,
        ib: IB | None = None,
    ) -> None:
        self._host = host or os.environ.get("IB_HOST", "127.0.0.1")
        self._port = port
        # live_engine/ib_broker.py가 client_id=1(데이터)/2(주문)을 이미 씀 — 기본값 1을 쓰면
        # 라이브 봇 구동 중 오더플로우 스트림을 동시에 열 때 같은 IB Gateway에 충돌.
        self._client_id = client_id if client_id is not None else int(
            os.environ.get("IB_ORDERFLOW_CLIENT_ID", "20")
        )
        self._ib = ib if ib is not None else IB()

    def _contract(self, symbol: str) -> Contract:
        exchange = _FUTURES_SYMBOLS.get(symbol)
        if exchange:
            return Future(symbol=symbol, exchange=exchange, currency="USD")
        return Stock(symbol, "SMART", "USD")

    async def _resolve_contract(self, contract: Contract) -> Contract:
        """만기월 미지정 선물은 qualify가 ambiguous로 실패(conId=0으로 남음) —
        그 경우 최근월물(front month)을 reqContractDetailsAsync로 직접 골라온다."""
        await self._ib.qualifyContractsAsync(contract)
        if contract.conId:
            return contract

        details = await self._ib.reqContractDetailsAsync(contract)
        if not details:
            raise ValueError(f"IB: no contract details resolved for {contract.symbol}")

        today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        candidates = sorted(details, key=lambda d: d.contract.lastTradeDateOrContractMonth)
        for d in candidates:
            if d.contract.lastTradeDateOrContractMonth >= today:
                return d.contract
        return candidates[-1].contract

    async def stream(
        self, symbol: str, connect_timeout: float = 15.0
    ) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=connect_timeout)
        contract = await self._resolve_contract(self._contract(symbol))

        last_ticker = self._ib.reqTickByTickData(contract, "Last")
        bidask_ticker = self._ib.reqTickByTickData(contract, "BidAsk")
        depth_ticker = self._ib.reqMktDepth(contract, numRows=DEPTH_ROWS)

        last_iter = last_ticker.updateEvent.__aiter__()
        bidask_iter = bidask_ticker.updateEvent.__aiter__()
        depth_iter = depth_ticker.updateEvent.__aiter__()

        last_task = asyncio.ensure_future(last_iter.__anext__())
        bidask_task = asyncio.ensure_future(bidask_iter.__anext__())
        depth_task = asyncio.ensure_future(depth_iter.__anext__())

        best_bid: float | None = None
        best_ask: float | None = None

        try:
            while True:
                done, _ = await asyncio.wait(
                    {last_task, bidask_task, depth_task}, return_when=asyncio.FIRST_COMPLETED
                )

                if bidask_task in done:
                    try:
                        bidask_task.result()
                    except StopAsyncIteration:
                        return
                    for tick in bidask_ticker.tickByTicks:
                        best_bid, best_ask = tick.bidPrice, tick.askPrice
                    bidask_ticker.tickByTicks.clear()
                    bidask_task = asyncio.ensure_future(bidask_iter.__anext__())

                if last_task in done:
                    try:
                        last_task.result()
                    except StopAsyncIteration:
                        return
                    for tick in last_ticker.tickByTicks:
                        if best_bid is not None and best_ask is not None:
                            side = classify(tick.price, best_bid, best_ask)
                            yield TradeEvent(
                                symbol=symbol,
                                ts=tick.time.timestamp(),
                                price=tick.price,
                                size=tick.size,
                                side=side,
                            )
                    last_ticker.tickByTicks.clear()
                    last_task = asyncio.ensure_future(last_iter.__anext__())

                if depth_task in done:
                    try:
                        depth_task.result()
                    except StopAsyncIteration:
                        return
                    yield OrderBookSnapshot(
                        symbol=symbol,
                        ts=dt.datetime.now(dt.timezone.utc).timestamp(),
                        bids=[OrderBookLevel(price=lv.price, size=lv.size) for lv in depth_ticker.domBids],
                        asks=[OrderBookLevel(price=lv.price, size=lv.size) for lv in depth_ticker.domAsks],
                    )
                    depth_task = asyncio.ensure_future(depth_iter.__anext__())
        finally:
            for task in (last_task, bidask_task, depth_task):
                if not task.done():
                    task.cancel()
