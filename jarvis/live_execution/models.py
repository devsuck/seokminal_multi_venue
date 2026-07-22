"""Live Execution 자료형 (P8.1) — 첫 라이브 집행 경계. **사람 게이트 전용.**

ExecutionIntent → Decision READY → Readiness Certificate READY → 사람 ARM →
LiveExecutionRequest → BrokerExecutionAdapter → LiveExecutionResponse.
**자율 트레이딩 없음·무인 집행 없음·스케줄러 트리거 없음·자동 자본 배치 없음.**
브로커 write 능력은 오직 [READY 인증서 + 사람 ARM + 명시적 호출] 뒤에서만.
결정적·append-only. 실브로커 어댑터는 기본 비활성(자율레벨<MIN_LIVE, 자격증명 없음).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"


@dataclass(frozen=True)
class LiveExecutionRequest:
    request_id: str
    intent_id: str
    broker: str                # mock | ib | kis
    symbol: str
    side: str                  # BUY | SELL
    quantity: float
    limit_price: float | None
    created_at: str
    arm_id: str                # 사람 ARM 레코드 식별자

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LiveExecutionResponse:
    request_id: str
    broker_order_id: str
    status: str                # ACCEPTED | REJECTED
    reason: str = ""
    timestamp: str = ""
    response_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def request_id(intent_id: str, arm_id: str, created_at: str) -> str:
    return "LXR:" + hashlib.sha1(f"{intent_id}|{arm_id}|{created_at}".encode()).hexdigest()[:12]


def request_hash(request: dict) -> str:
    blob = json.dumps(request, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def response_hash(request_id_: str, broker_order_id: str, status: str,
                  reason: str, timestamp: str) -> str:
    payload = {"request_id": request_id_, "broker_order_id": broker_order_id,
               "status": status, "reason": reason, "timestamp": timestamp}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
