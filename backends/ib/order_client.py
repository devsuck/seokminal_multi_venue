import asyncio
import os
import time

from ib_async import IB
from ib_async.contract import Option, Stock
from ib_async.order import UNSET_DOUBLE, LimitOrder, MarketOrder, Trade


class IBOrderClient:
    def __init__(
        self,
        host: str | None = None,
        port: int = 7497,
        client_id: int = 2,
        ib: IB | None = None,
    ) -> None:
        # WSL 등에서 TWS가 다른 호스트에 있을 때 IB_HOST로 지정 (기본 로컬)
        self._host = host or os.environ.get("IB_HOST", "127.0.0.1")
        self._port = port
        self._client_id = client_id
        self._ib = ib if ib is not None else IB()

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        wait_fill: bool = False,
    ) -> dict:
        """Place an order. When ``wait_fill`` is True, wait (briefly) for the
        order to reach a terminal state so the returned dict carries the real
        ``avg_fill_price`` — needed for accurate live P&L on market orders."""
        await self._ensure_connected()
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)

        if order_type == "LIMIT":
            order = LimitOrder(side, quantity, limit_price)
        else:
            order = MarketOrder(side, quantity)

        trade = self._ib.placeOrder(contract, order)
        if wait_fill:
            await self._await_fill(trade)
        return self._to_dict(trade)

    async def place_option_order(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        right: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        wait_fill: bool = False,
    ) -> dict:
        """Place a single-leg option order. ``quantity`` is contract count
        (1 contract = 100 shares of the underlying)."""
        await self._ensure_connected()
        contract = Option(
            symbol=symbol,
            lastTradeDateOrContractMonth=expiry,
            strike=strike,
            right=right,
            exchange="SMART",
            currency="USD",
        )
        await self._ib.qualifyContractsAsync(contract)

        if order_type == "LIMIT":
            order = LimitOrder(side, quantity, limit_price)
        else:
            order = MarketOrder(side, quantity)

        trade = self._ib.placeOrder(contract, order)
        if wait_fill:
            await self._await_fill(trade)
        return self._to_dict(trade)

    async def _await_fill(self, trade: Trade, timeout: float = 6.0) -> None:
        """Poll until the order is done (filled/cancelled) or times out."""
        terminal = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}
        deadline = time.monotonic() + timeout
        while trade.orderStatus.status not in terminal and time.monotonic() < deadline:
            await asyncio.sleep(0.2)

    async def get_intraday_bars(
        self, symbol: str, bar_size: str = "5 mins", duration: str = "2 D"
    ) -> list[dict]:
        """Recent intraday bars as intraday_score-shaped dicts (t/o/h/l/c/v).
        Reuses this client's IB connection so a live day-trade tick reads data
        and executes over a single session (no source mismatch)."""
        await self._ensure_connected()
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )
        return [
            {"t": b.date, "o": float(b.open), "h": float(b.high),
             "l": float(b.low), "c": float(b.close), "v": float(b.volume)}
            for b in bars
        ]

    async def get_order_status(self, order_id: int) -> dict | None:
        await self._ensure_connected()
        trade = self._find_trade(order_id)
        if trade is None:
            return None
        return self._to_dict(trade)

    async def cancel_order(self, order_id: int) -> dict:
        await self._ensure_connected()
        trade = self._find_trade(order_id)
        if trade is None:
            raise ValueError(f"no known order with order_id={order_id}")

        cancelled = self._ib.cancelOrder(trade.order)
        if cancelled is None:
            raise ValueError(f"no known order with order_id={order_id}")
        return self._to_dict(cancelled)

    async def get_positions(self) -> list[dict]:
        """Held IB positions: [{symbol, qty(signed), avg_price}]."""
        await self._ensure_connected()
        out = []
        for p in self._ib.positions():
            q = float(p.position)
            if q != 0:
                out.append({"symbol": p.contract.symbol, "qty": q,
                            "avg_price": float(p.avgCost)})
        return out

    async def _ensure_connected(self) -> None:
        if not self._ib.isConnected():
            await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=4)

    def _find_trade(self, order_id: int) -> Trade | None:
        for trade in self._ib.trades():
            if trade.order.orderId == order_id:
                return trade
        return None

    @staticmethod
    def _to_dict(trade: Trade) -> dict:
        avg = getattr(trade.orderStatus, "avgFillPrice", None)
        avg_fill = None if avg is None or avg == UNSET_DOUBLE or avg == 0 else float(avg)
        return {
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "remaining": trade.orderStatus.remaining,
            "avg_fill_price": avg_fill,
        }

    async def close(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
