"""IB broker adapter. Routes NASDAQ/ARCA instruments to IB async."""
import time
from collections.abc import AsyncIterator

from backends.ib.client import IBClient
from backends.ib.order_client import IBOrderClient
from live_engine.broker_interface import BrokerInterface, OrderResult, Position, PriceTick


def _instrument_to_symbol(instrument_id: str) -> str:
    """'AAPL.NASDAQ' → 'AAPL'"""
    return instrument_id.split(".")[0]


class IBBroker(BrokerInterface):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
    ) -> None:
        self._data_client = IBClient(host=host, port=port, client_id=1)
        self._order_client = IBOrderClient(host=host, port=port, client_id=2)

    async def place_order(
        self,
        instrument_id: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: float | None = None,
    ) -> OrderResult:
        symbol = _instrument_to_symbol(instrument_id)
        result = await self._order_client.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        return OrderResult(
            order_id=str(result["order_id"]),
            status=result["status"],
            filled=result["filled"],
            remaining=result["remaining"],
        )

    async def get_position(self, instrument_id: str) -> Position | None:
        """Look up the held IB position for reconciliation (None if flat/unknown)."""
        symbol = _instrument_to_symbol(instrument_id)
        await self._order_client._ensure_connected()
        for pos in self._order_client._ib.positions():
            if pos.contract.symbol == symbol and pos.position:
                qty = float(pos.position)
                return Position(
                    instrument_id=instrument_id,
                    qty=abs(qty),
                    avg_price=float(pos.avgCost),
                    side="LONG" if qty > 0 else "SHORT",
                )
        return None

    async def cancel_order(self, order_id: str) -> OrderResult:
        result = await self._order_client.cancel_order(int(order_id))
        return OrderResult(
            order_id=str(result["order_id"]),
            status=result["status"],
            filled=result["filled"],
            remaining=result["remaining"],
        )

    async def stream_prices(self, instrument_id: str) -> AsyncIterator[PriceTick]:
        symbol = _instrument_to_symbol(instrument_id)
        async for tick in self._data_client.stream_trades(symbol):
            yield PriceTick(
                instrument_id=instrument_id,
                price=float(tick.price),
                ts_ns=int(time.time_ns()),
            )

    async def close(self) -> None:
        if self._data_client._ib.isConnected():
            self._data_client._ib.disconnect()
        if self._order_client._ib.isConnected():
            self._order_client._ib.disconnect()
