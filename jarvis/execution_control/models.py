"""Execution Control 자료형 (P7.4) — 통제된 '의도' 계층(집행 아님).

ExecutionIntent → (6 checks) → ExecutionDecision(BLOCKED/READY).
**ExecutionDecision은 주문이 아니다 — 감사가능한 지시 후보일 뿐.** 결정적·읽기전용.
집행 게이트웨이 import 금지·브로커 없음·주문 없음.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import asdict, dataclass, field

BLOCKED = "BLOCKED"
READY = "READY"

DEFAULT_EXPIRY_HOURS = 24.0


@dataclass(frozen=True)
class ExecutionIntent:
    intent_id: str
    strategy: str
    symbol: str
    side: str                 # BUY | SELL | HOLD
    quantity: float
    target_weight: float
    source_proposal_id: str
    created_at: str
    expiry: str = ""          # 만료 타임스탬프

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ControlCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ARMRequirement:
    required: bool
    present: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionDecision:
    intent_id: str
    status: str               # BLOCKED | READY
    checks: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    timestamp: str = ""
    hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def intent_id(source_proposal_id: str, strategy: str, symbol: str, side: str) -> str:
    return "EI:" + hashlib.sha1(
        f"{source_proposal_id}|{strategy}|{symbol}|{side}".encode()).hexdigest()[:12]


def decision_hash(intent_id_: str, status: str, checks: list, timestamp: str) -> str:
    import json
    payload = {"intent_id": intent_id_, "status": status, "timestamp": timestamp,
               "checks": [(c["name"], c["passed"]) for c in checks]}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def add_hours(ts: str, hours: float) -> str:
    d = _parse(ts)
    if d is None:
        return ""
    return (d + _dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_expired(expiry: str, now: str) -> bool:
    e, n = _parse(expiry), _parse(now)
    return e is not None and n is not None and n > e
