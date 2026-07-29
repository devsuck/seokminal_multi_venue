"""Broker Read-Only 자료형 (P7.1) — 읽기전용 라이브환경 경계. **주문 능력 없음.**

계좌/포지션/잔고/주문이력 정규화 모델 + 헬스 + 리컨실리에이션. 결정적·타임스탬프.
집행 게이트웨이/리스크/레지스트리와 무관(import 금지).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    equity: float
    buying_power: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    quantity: float
    avg_price: float
    market_value: float
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BrokerHealth:
    connected: bool
    stale: bool
    error: str | None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationReport:
    timestamp: str
    matched: list = field(default_factory=list)
    missing_in_broker: list = field(default_factory=list)
    missing_in_paper: list = field(default_factory=list)
    quantity_difference: dict = field(default_factory=dict)
    value_difference: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
