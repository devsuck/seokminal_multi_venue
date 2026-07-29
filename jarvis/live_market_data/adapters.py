"""Live streaming 어댑터 (P7.2) — Mock(결정적·리플레이) + IB/KIS 플레이스홀더.

**자격증명 없음·네트워크 없음·주문 메서드 없음.** IB/KIS는 미구성 플레이스홀더
(주문가능 브로커 백엔드 미import — 경계 격리).
"""
from __future__ import annotations

from jarvis.live_market_data.models import MarketTick, parse_ts
from jarvis.live_market_data.provider import LiveMarketDataProvider
from jarvis.live_market_data.quality import tick_quality


def simulate_ticks(base_price: float, n: int, start_ts: str, step_seconds: int = 1,
                   seed: int = 42) -> list[dict]:
    """결정적 틱 경로(LCG, 난수 아님). 리플레이 가능."""
    import datetime as _dt
    t0 = parse_ts(start_ts) or _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    x = seed
    price = base_price
    out = []
    for i in range(n):
        x = (1103515245 * x + 12345) % (2 ** 31)
        delta = (x / 2 ** 31 - 0.5) * 0.02          # ±1%
        price = round(price * (1 + delta), 4)
        ts = (t0 + _dt.timedelta(seconds=i * step_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"price": price, "bid": round(price * 0.999, 4),
                    "ask": round(price * 1.001, 4), "volume": 100.0, "timestamp": ts})
    return out


class MockStreamingProvider(LiveMarketDataProvider):
    """결정적 시뮬 틱. ticks={symbol: [tick dict]}. clock 설정 시 no-lookahead + 스테일."""
    source_name = "mock_stream"

    def __init__(self, ticks: dict | None = None, clock: str | None = None,
                 stale_seconds: float = 60.0) -> None:
        self._ticks: dict = {}
        for sym, series in (ticks or {}).items():
            s = sorted(series, key=lambda t: t["timestamp"])
            self._ticks[sym] = s
        self._clock = clock
        self._stale = stale_seconds
        self._subscribed: set = set()

    def subscribe(self, symbols: list[str]) -> None:
        self._subscribed |= set(symbols)

    def latest(self, symbol: str) -> MarketTick | None:
        series = self._ticks.get(symbol)
        if not series:
            return None
        elig = [t for t in series if self._clock is None or t["timestamp"] <= self._clock]
        if not elig:
            return None
        raw = elig[-1]
        prev = elig[-2] if len(elig) > 1 else None
        q = tick_quality(raw["timestamp"], raw["price"],
                         prev["timestamp"] if prev else None, prev["price"] if prev else None,
                         self._clock, stale_seconds=self._stale)
        return MarketTick(symbol=symbol, price=raw["price"], bid=raw.get("bid", raw["price"]),
                          ask=raw.get("ask", raw["price"]), volume=raw.get("volume", 0.0),
                          timestamp=raw["timestamp"], source="mock_stream", quality=q)

    def health_check(self) -> dict:
        return {"status": "ok" if self._ticks else "empty", "provider": "MockStreamingProvider",
                "source": "mock_stream", "connected": bool(self._ticks),
                "subscribed": sorted(self._subscribed), "n_symbols": len(self._ticks)}


class _UnconfiguredStream(LiveMarketDataProvider):
    """미구성 스트리밍 플레이스홀더 — 자격증명/네트워크 없음. disconnected."""
    source_name = "unconfigured_stream"
    broker_name = "generic"

    def __init__(self, clock: str = "") -> None:
        self._ts = clock

    def subscribe(self, symbols: list[str]) -> None:
        return None

    def latest(self, symbol: str):
        return None

    def health_check(self) -> dict:
        return {"status": "not_configured", "provider": type(self).__name__,
                "source": self.source_name, "connected": False, "stale": True,
                "error": f"not_configured ({self.broker_name} streaming placeholder — "
                         "자격증명/네트워크 없음)"}


class IBStreamingProvider(_UnconfiguredStream):
    """IB 스트리밍 플레이스홀더 — 미구성(주문가능 IB 백엔드 미import)."""
    source_name = "ib_stream"
    broker_name = "ib"


class KISStreamingProvider(_UnconfiguredStream):
    """KIS 스트리밍 플레이스홀더 — 미구성(주문가능 KIS 백엔드 미import)."""
    source_name = "kis_stream"
    broker_name = "kis"
