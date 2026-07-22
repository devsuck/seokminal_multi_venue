"""Market Data 자료형 (P6.4) — 읽기전용 시장데이터. 주문 능력 없음.

PriceSnapshot(symbol/price/timestamp/source/quality). OHLCVBar. 결정적.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field

# quality 등급
OK = "OK"
STALE = "STALE"
MISSING = "MISSING"
SUSPECT = "SUSPECT"       # 이상 점프
DUPLICATE = "DUPLICATE"
FUTURE = "FUTURE"


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    price: float
    timestamp: str
    source: str = ""
    quality: str = OK

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OHLCVBar:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MarketDataQualityReport:
    symbol: str
    n_bars: int
    quality_score: float
    issues: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_ts(ts: str):
    """ISO/date 파싱 → datetime(UTC). 실패 시 None."""
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d"):
        try:
            if fmt is None:
                d = _dt.datetime.fromisoformat(s)
            else:
                d = _dt.datetime.strptime(str(ts).strip(), fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=_dt.timezone.utc)
            return d
        except ValueError:
            continue
    return None


def hours_between(a_ts: str, b_ts: str) -> float | None:
    a, b = parse_ts(a_ts), parse_ts(b_ts)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0
