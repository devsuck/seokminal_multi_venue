"""Broker Execution Adapters (P8.1) — 브로커 주문 인터페이스. **write 능력.**

BrokerExecutionAdapter(ABC): submit_order · cancel_order · health_check.
  MockExecutionAdapter  결정적·시뮬 응답·**자본 이동 없음**(테스트/데모).
  IBExecutionAdapter / KISExecutionAdapter  **자리표시자만 — 자격증명 없음·기본 비활성.**

실브로커(IB/KIS) 활성 조건: 자율레벨>=MIN_LIVE AND 자격증명 존재. 현주소 = 둘 다 미충족 →
비활성(honest CLOSED). 자율 트리거 없음 — 명시적 호출로만 사용.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from jarvis.config import live_execution_enabled


class BrokerExecutionAdapter(ABC):
    """브로커 집행 어댑터 인터페이스. 구현체만 실제 write를 시도한다."""

    name: str = "abstract"

    @abstractmethod
    def submit_order(self, request: dict) -> dict:
        """주문 제출 → {accepted: bool, broker_order_id: str, reason: str}."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> dict:
        """주문 취소 → {cancelled: bool, reason: str}."""
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict:
        """어댑터 상태 → {name, enabled, connected, reason}."""
        raise NotImplementedError


class MockExecutionAdapter(BrokerExecutionAdapter):
    """결정적 모의 브로커 — 시뮬 응답만, **실자본/실주문 없음.**"""

    name = "mock"

    def submit_order(self, request: dict) -> dict:
        # 결정적 broker_order_id(요청 식별자 해시). 어떤 자본도 이동하지 않음.
        rid = request.get("request_id", "")
        boid = "MOCK:" + hashlib.sha1(rid.encode()).hexdigest()[:12]
        return {"accepted": True, "broker_order_id": boid,
                "reason": "mock accept — 시뮬 응답, 실자본 없음"}

    def cancel_order(self, broker_order_id: str) -> dict:
        return {"cancelled": True, "reason": "mock cancel — 시뮬"}

    def health_check(self) -> dict:
        return {"name": self.name, "enabled": True, "connected": True,
                "reason": "mock — 실브로커 아님·자본 없음"}


class _DisabledLiveAdapter(BrokerExecutionAdapter):
    """실브로커 자리표시자 — 자격증명 없음·기본 비활성. 절대 자동 활성화 안 됨."""

    name = "disabled"

    def __init__(self, credentials: dict | None = None) -> None:
        # 자격증명 미주입 → 없음. 활성 = 자율레벨>=MIN_LIVE AND 자격증명 존재.
        self._creds = credentials or {}

    def _enabled(self) -> bool:
        return bool(self._creds) and live_execution_enabled()

    def submit_order(self, request: dict) -> dict:
        return {"accepted": False, "broker_order_id": "",
                "reason": f"adapter_disabled({self.name}: 자격증명 없음/자율레벨 미달)"}

    def cancel_order(self, broker_order_id: str) -> dict:
        return {"cancelled": False, "reason": f"adapter_disabled({self.name})"}

    def health_check(self) -> dict:
        return {"name": self.name, "enabled": self._enabled(), "connected": False,
                "reason": "placeholder — 자격증명 없음·자율레벨<MIN_LIVE"}


class IBExecutionAdapter(_DisabledLiveAdapter):
    """Interactive Brokers 집행 자리표시자 — 비활성."""
    name = "ib"


class KISExecutionAdapter(_DisabledLiveAdapter):
    """한국투자증권(KIS) 집행 자리표시자 — 비활성."""
    name = "kis"


def get_adapter(broker: str, credentials: dict | None = None) -> BrokerExecutionAdapter:
    if broker == "mock":
        return MockExecutionAdapter()
    if broker == "ib":
        return IBExecutionAdapter(credentials)
    if broker == "kis":
        return KISExecutionAdapter(credentials)
    raise ValueError(f"unknown broker: {broker}")
