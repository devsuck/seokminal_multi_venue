"""LiveMarketDataProvider 인터페이스 (P7.2) — 읽기전용 스트리밍. **주문 능력 없음.**

메서드: subscribe(symbols) · latest(symbol) · snapshot(symbols) · health_check().
집행/브로커주문 import 금지. 모든 틱 타임스탬프 필수.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.live_market_data.models import MarketTick


class LiveMarketDataProvider(ABC):
    source_name: str = "base"

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None:
        """구독 등록(읽기 관심 심볼). 주문 아님."""

    @abstractmethod
    def latest(self, symbol: str) -> MarketTick | None:
        """최신 틱(없으면 None). no-lookahead."""

    def snapshot(self, symbols: list[str]) -> dict:
        return {s: self.latest(s) for s in symbols}

    @abstractmethod
    def health_check(self) -> dict:
        """연결/구독/스테일 상태."""
