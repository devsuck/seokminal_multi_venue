"""Order Lifecycle 자료형 (P8.2) — 라이브 집행 요청/응답의 '생애주기' 관측 기록.

**주문 생성/집행 아님.** P8.1 요청·응답을 관측하여 상태전이를 해시체인 이벤트로 기록만.
OrderLifecycleState(enum) · OrderLifecycleEvent(event_hash·previous_hash 체인).
결정적·append-only·재현가능. 브로커 호출 없음·게이트웨이 없음·포지션 변경 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum

GENESIS = "GENESIS"   # 최초 이벤트의 previous_hash


class OrderLifecycleState(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

    def __str__(self) -> str:   # JSON/로그에서 값만
        return self.value


# 종료(터미널) 상태 — 이후 전이 없음
TERMINAL = frozenset({
    OrderLifecycleState.FILLED.value, OrderLifecycleState.REJECTED.value,
    OrderLifecycleState.CANCELLED.value, OrderLifecycleState.FAILED.value,
    OrderLifecycleState.EXPIRED.value,
})


@dataclass(frozen=True)
class OrderLifecycleEvent:
    event_id: str
    order_id: str
    previous_state: str        # "" for genesis(CREATED)
    new_state: str
    timestamp: str
    reason: str = ""
    source: str = "manager"
    previous_hash: str = GENESIS
    event_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def event_id(order_id: str, new_state: str, timestamp: str) -> str:
    """논리적 이벤트 키(order_id·목표상태·시각). 동일 이벤트 재전달 → 동일 id(멱등).

    서로 다른 부분체결은 시각이 달라 id도 달라짐 → 각각 기록. 체인 무결성은
    event_hash/previous_hash가 담당(id와 독립).
    """
    raw = f"{order_id}|{new_state}|{timestamp}"
    return "OLE:" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def event_hash(event_id_: str, order_id: str, previous_state: str, new_state: str,
               timestamp: str, reason: str, source: str, previous_hash: str) -> str:
    payload = {"event_id": event_id_, "order_id": order_id,
               "previous_state": previous_state, "new_state": new_state,
               "timestamp": timestamp, "reason": reason, "source": source,
               "previous_hash": previous_hash}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
