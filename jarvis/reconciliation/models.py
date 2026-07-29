"""Reconciliation 자료형 (P7.3) — 페이퍼 vs 브로커 vs 라이브 대조. 집행 아님.

ControlEvent + ReconciliationReport + DriftThresholds. 읽기전용·결정적. 주문 없음.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# severity
OK = "OK"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
_RANK = {OK: 0, WARNING: 1, CRITICAL: 2}

# control event types
POSITION_DRIFT = "POSITION_DRIFT"
PRICE_DRIFT = "PRICE_DRIFT"
NAV_DRIFT = "NAV_DRIFT"
STALE_DATA = "STALE_DATA"
BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
EVENT_TYPES = [POSITION_DRIFT, PRICE_DRIFT, NAV_DRIFT, STALE_DATA, BROKER_UNAVAILABLE]


@dataclass(frozen=True)
class DriftThresholds:
    quantity_tol: float = 1e-6
    value_tol: float = 0.01
    price_drift_warn: float = 0.005      # 0.5%
    price_drift_critical: float = 0.02   # 2%
    nav_drift_warn: float = 0.01         # 1%
    nav_drift_critical: float = 0.05     # 5%


@dataclass(frozen=True)
class ControlEvent:
    type: str
    severity: str
    message: str
    timestamp: str
    source: str = "engine"   # paper | broker | live | engine

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationReport:
    timestamp: str
    matched_positions: list = field(default_factory=list)
    missing_in_broker: list = field(default_factory=list)
    missing_in_paper: list = field(default_factory=list)
    quantity_difference: dict = field(default_factory=dict)
    average_price_difference: dict = field(default_factory=dict)
    market_value_difference: dict = field(default_factory=dict)
    nav_difference: float | None = None
    severity: str = OK
    control_events: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def max_severity(events: list) -> str:
    sev = OK
    for e in events:
        s = e.severity if hasattr(e, "severity") else e.get("severity", OK)
        if _RANK.get(s, 0) > _RANK.get(sev, 0):
            sev = s
    return sev
