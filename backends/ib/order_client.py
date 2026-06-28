from ib_async import IB
from ib_async.contract import Stock
from ib_async.order import LimitOrder, MarketOrder, Trade


class IBOrderClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 2,
        ib: IB | None = None,
    ) -> None:
        self._host = host
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
    ) -> dict:
        await self._ensure_connected()
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)

        if order_type == "LIMIT":
            order = LimitOrder(side, quantity, limit_price)
        else:
            order = MarketOrder(side, quantity)

        trade = self._ib.placeOrder(contract, order)
        return self._to_dict(trade)

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

    async def _ensure_connected(self) -> None:
        if not self._ib.isConnected():
            await self._ib.connectAsync(self._host, self._port, self._client_id)

    def _find_trade(self, order_id: int) -> Trade | None:
        for trade in self._ib.trades():
            if trade.order.orderId == order_id:
                return trade
        return None

    @staticmethod
    def _to_dict(trade: Trade) -> dict:
        return {
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "remaining": trade.orderStatus.remaining,
        }

    async def close(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
