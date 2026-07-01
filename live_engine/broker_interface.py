"""Unified broker abstraction. KIS and IB both implement this."""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class PriceTick:
    instrument_id: str
    price: float
    ts_ns: int


@dataclass
class OrderResult:
    order_id: str
    status: str   # SUBMITTED | FILLED | PARTIAL | CANCELLED | ERROR
    filled: float
    remaining: float
    avg_fill_price: float | None = None  # actual fill price when known (None = use ref price)


@dataclass
class Position:
    instrument_id: str
    qty: float
    avg_price: float
    side: str          # LONG | SHORT | FLAT
    unrealized_pnl: float | None = None


@dataclass
class BotStatus:
    bot_id: str
    instrument_id: str
    running: bool
    position: str = "FLAT"  # LONG | SHORT | FLAT
    qty: float = 0.0
    last_price: float | None = None
    last_signal: str | None = None  # EMA_BUY | EMA_SELL | HOLD
    orders: list[OrderResult] = field(default_factory=list)
    error: str | None = None
    entry_price: float | None = None  # price when current position was opened


class BrokerInterface(ABC):
    """Abstract interface. Every broker adapter implements this."""

    @abstractmethod
    async def place_order(
        self,
        instrument_id: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: float | None = None,
    ) -> OrderResult:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResult:
        ...

    @abstractmethod
    async def stream_prices(self, instrument_id: str) -> AsyncIterator[PriceTick]:
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release connections."""
        ...

    async def get_position(self, instrument_id: str) -> Position | None:
        """Return the broker's current position, or None when not implemented.

        Used by the engine to reconcile its tracked position with reality on
        startup. The default returns None ("unknown") so adapters that don't
        implement it leave the engine to start flat, as before.
        """
        return None
