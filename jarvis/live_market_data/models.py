"""Live Market Data 자료형 (P7.2) — 실시간 읽기전용 틱. **주문 능력 없음.**

MarketTick(symbol/price/bid/ask/volume/timestamp/source/quality). 결정적.
quality 등급은 P6.4 market_data와 호환(재사용).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# P6.4 quality 어휘 재사용(호환)
from jarvis.market_data.models import (  # noqa: F401
    DUPLICATE,
    FUTURE,
    MISSING,
    OK,
    STALE,
    SUSPECT,
    hours_between,
    parse_ts,
)


@dataclass(frozen=True)
class MarketTick:
    symbol: str
    price: float
    bid: float
    ask: float
    volume: float
    timestamp: str
    source: str = ""
    quality: str = OK

    def to_dict(self) -> dict:
        return asdict(self)
