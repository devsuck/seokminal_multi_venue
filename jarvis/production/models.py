"""Production Readiness 자료형 (P6.1) — 연구/제안 ↔ 집행 경계.

**라이브 트레이딩 아님.** 제어된 프로덕션 인터페이스만. 주문 없음·브로커 없음.
집행 status 없음(GENERATED..EXPIRED). 집행 게이트웨이 무수정.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import asdict, dataclass, field

# 제안 상태(집행 상태 없음)
STATUSES = ["GENERATED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "EXPIRED"]

# 게이트가 프로덕션-레디로 인정하는 registry 상태(paper_active는 아직 아님 — 정직)
PRODUCTION_READY_STATUSES = {"live_candidate", "micro_live", "constrained_live", "live"}

EXPIRY_HOURS = 48          # 승인 만료
FRESHNESS_HOURS = 24       # 게이트 데이터 신선도


@dataclass(frozen=True)
class ProductionProposal:
    proposal_id: str
    source: str            # portfolio_orchestrator | planner | manual | demo
    strategy: str
    allocation: dict = field(default_factory=dict)
    risk_state: dict = field(default_factory=dict)
    rationale: list = field(default_factory=list)
    created_at: str = ""
    status: str = "GENERATED"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GateDecision:
    decision: str          # ALLOW | BLOCK
    reason: str
    failed_checks: list = field(default_factory=list)
    timestamp: str = ""
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalRecord:
    proposal_id: str
    decision: str          # APPROVED | REJECTED
    approver: str
    reason: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


def make_proposal_id(source: str, strategy: str, created_at: str) -> str:
    return "PP:" + hashlib.sha1(f"{source}|{strategy}|{created_at}".encode()).hexdigest()[:12]


def _parse(ts: str) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def hours_between(a: str, b: str) -> float | None:
    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return None
    return (db - da).total_seconds() / 3600.0


def is_expired(created_at: str, now: str, expiry_hours: float = EXPIRY_HOURS) -> bool:
    h = hours_between(created_at, now)
    return h is not None and h > expiry_hours
