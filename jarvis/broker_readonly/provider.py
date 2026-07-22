"""BrokerReadOnlyProvider 인터페이스 (P7.1) — 전부 읽기전용·결정적·타임스탬프.

메서드: account_snapshot · positions · balances · orders_history · health_check.
**write/order 메서드 없음.** 집행 게이트웨이 import 금지(경계 분리).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.broker_readonly.models import AccountSnapshot, BrokerHealth, BrokerPosition


class BrokerReadOnlyProvider(ABC):
    source_name: str = "base"

    @abstractmethod
    def account_snapshot(self) -> AccountSnapshot | None:
        """계좌 스냅샷(현금/자본/매수여력). 없으면 None."""

    @abstractmethod
    def positions(self) -> list[BrokerPosition]:
        """보유 포지션(읽기전용)."""

    @abstractmethod
    def balances(self) -> dict:
        """잔고 요약."""

    @abstractmethod
    def orders_history(self) -> list[dict]:
        """과거 주문 이력(읽기전용 — 신규 주문 아님)."""

    @abstractmethod
    def health_check(self) -> BrokerHealth:
        """연결/스테일/에러 상태."""
