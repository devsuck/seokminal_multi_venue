"""Broker Read-Only 어댑터 (P7.1) — Mock + IB/KIS 플레이스홀더.

**자격증명 없음·네트워크 없음·주문 엔드포인트 없음.** IB/KIS는 미구성 플레이스홀더
(주문가능 브로커 백엔드 클라이언트를 import하지 않음 — 경계 격리).
"""
from __future__ import annotations

from jarvis.broker_readonly.models import (
    AccountSnapshot,
    BrokerHealth,
    BrokerPosition,
)
from jarvis.broker_readonly.provider import BrokerReadOnlyProvider


class MockBrokerProvider(BrokerReadOnlyProvider):
    """결정적 주입형(테스트/시연). 주문 능력 없음."""
    source_name = "mock"

    def __init__(self, account: dict | None = None, positions: list | None = None,
                 orders: list | None = None, timestamp: str = "",
                 connected: bool = True, stale: bool = False, error: str | None = None) -> None:
        self._account = account
        self._positions = positions or []
        self._orders = orders or []
        self._ts = timestamp
        self._connected = connected
        self._stale = stale
        self._error = error

    def account_snapshot(self) -> AccountSnapshot | None:
        if not self._account:
            return None
        a = self._account
        return AccountSnapshot(cash=float(a.get("cash", 0.0)), equity=float(a.get("equity", 0.0)),
                               buying_power=float(a.get("buying_power", 0.0)), timestamp=self._ts)

    def positions(self) -> list[BrokerPosition]:
        return [BrokerPosition(symbol=p["symbol"], quantity=float(p["quantity"]),
                               avg_price=float(p.get("avg_price", 0.0)),
                               market_value=float(p.get("market_value", 0.0)),
                               timestamp=self._ts)
                for p in sorted(self._positions, key=lambda x: x["symbol"])]

    def balances(self) -> dict:
        a = self._account or {}
        return {"cash": float(a.get("cash", 0.0)), "equity": float(a.get("equity", 0.0)),
                "buying_power": float(a.get("buying_power", 0.0)), "timestamp": self._ts}

    def orders_history(self) -> list[dict]:
        return list(self._orders)

    def health_check(self) -> BrokerHealth:
        return BrokerHealth(connected=self._connected, stale=self._stale,
                            error=self._error, timestamp=self._ts)


class _UnconfiguredBroker(BrokerReadOnlyProvider):
    """미구성 플레이스홀더 — 자격증명/네트워크 없음. 전부 빈값 + disconnected."""
    source_name = "unconfigured"
    broker_name = "generic"

    def __init__(self, timestamp: str = "") -> None:
        self._ts = timestamp

    def account_snapshot(self):
        return None

    def positions(self):
        return []

    def balances(self):
        return {}

    def orders_history(self):
        return []

    def health_check(self) -> BrokerHealth:
        return BrokerHealth(connected=False, stale=True,
                            error=f"not_configured ({self.broker_name} read-only placeholder — "
                                  "자격증명/네트워크 없음)", timestamp=self._ts)


class IBReadOnlyProvider(_UnconfiguredBroker):
    """IB 읽기전용 플레이스홀더 — 미구성(주문가능 IB 백엔드 미import)."""
    source_name = "ib_readonly"
    broker_name = "ib"


class KISReadOnlyProvider(_UnconfiguredBroker):
    """KIS 읽기전용 플레이스홀더 — 미구성(주문가능 KIS 백엔드 미import)."""
    source_name = "kis_readonly"
    broker_name = "kis"
