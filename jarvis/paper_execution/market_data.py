"""Market Data Adapter (P6.3) — 페이퍼 밸류에이션용 읽기전용 가격. 브로커 없음.

주입 가능·결정적. 심볼 = strategy_id(페이퍼 모델은 전략단위 유닛 거래).
가격 없으면 None(결측 처리는 valuation/monitor가).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    price: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


class PriceProvider(Protocol):
    def get(self, symbol: str, timestamp: str) -> PriceSnapshot | None:
        ...


class StaticPriceProvider:
    """명시 가격표(테스트/주입). {symbol: price} 또는 {symbol: (price, ts)}."""

    def __init__(self, prices: dict, timestamp: str = "") -> None:
        self._prices = prices
        self._ts = timestamp

    def get(self, symbol: str, timestamp: str) -> PriceSnapshot | None:
        if symbol not in self._prices:
            return None
        v = self._prices[symbol]
        if isinstance(v, tuple):
            price, ts = v
        else:
            price, ts = v, (self._ts or timestamp)
        return PriceSnapshot(symbol=symbol, price=float(price), timestamp=ts)


class FlatMarkProvider:
    """시장데이터 없을 때 진입평단으로 flat mark(무변동, 정직). {symbol: avg_price}."""

    def __init__(self, avg_prices: dict, timestamp: str = "") -> None:
        self._avg = avg_prices
        self._ts = timestamp

    def get(self, symbol: str, timestamp: str) -> PriceSnapshot | None:
        if symbol not in self._avg:
            return None
        return PriceSnapshot(symbol=symbol, price=float(self._avg[symbol]),
                             timestamp=self._ts or timestamp)


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def price_age_hours(snap: PriceSnapshot | None, now: str) -> float | None:
    if snap is None:
        return None
    a, b = _parse(snap.timestamp), _parse(now)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0
