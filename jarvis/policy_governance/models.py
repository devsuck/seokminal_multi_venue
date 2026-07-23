"""Policy & Configuration Governance 자료형 (P9.7) — 정책/설정 변경의 관리·감사 전용.

**실제 변경 실행 없음.** 정책 정의 → 변경요청(상태머신) → 승인 기록 → 스냅샷 → drift 감지만.
**config/risk threshold/autonomy/permission/kill switch 무변경·execution 호출 없음.**
불변 버전·append-only 해시체인·결정적. record_hash = 콘텐츠(체인 필드 제외) sha256.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Change Request 상태머신 ──
DRAFT = "DRAFT"
REQUESTED = "REQUESTED"
REVIEWED = "REVIEWED"
APPROVED = "APPROVED"
ACTIVE = "ACTIVE"
REJECTED = "REJECTED"

CHANGE_STATES = (DRAFT, REQUESTED, REVIEWED, APPROVED, ACTIVE, REJECTED)

ALLOWED_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {REQUESTED},
    REQUESTED: {REVIEWED},
    REVIEWED: {APPROVED, REJECTED},
    APPROVED: {ACTIVE},
    ACTIVE: set(),
    REJECTED: set(),
}
_PENDING = {DRAFT, REQUESTED, REVIEWED}
_APPROVED_SET = {APPROVED, ACTIVE}

# ── 승인 결정 ──
APPROVE = "APPROVE"
REJECT = "REJECT"
_DECISIONS = {APPROVE, REJECT}

# ── Drift 결과 ──
NO_DRIFT = "NO_DRIFT"
WARNING_DRIFT = "WARNING_DRIFT"
CRITICAL_DRIFT = "CRITICAL_DRIFT"

_DRIFT_PENALTY = {CRITICAL_DRIFT: 34, WARNING_DRIFT: 8, NO_DRIFT: 0}


class IllegalTransition(Exception):
    """차단된 변경요청 상태 전이."""


class ImmutablePolicyError(Exception):
    """불변 정책 버전 위반(동일 policy_id+version 내용 상이)."""


class ApprovalError(Exception):
    """승인 거버넌스 위반(승인자 없음·해시 불일치 등)."""


class DriftError(Exception):
    """drift 감지 전제 위반(스냅샷 없음 등)."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def is_valid_decision(d: str) -> bool:
    return d in _DECISIONS


def is_pending(status: str) -> bool:
    return status in _PENDING


def is_approved(status: str) -> bool:
    return status in _APPROVED_SET


# ── 해시 ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def policy_hash(policy_id: str, name: str, category: str, version: str,
                parameters: dict, description: str) -> str:
    """정책 콘텐츠 해시(메타데이터 제외 — 버전 불변 판정용)."""
    return _digest({"policy_id": policy_id, "name": name, "category": category,
                    "version": version, "parameters": parameters, "description": description})


def change_id(policy_id: str, new_hash: str, requested_by: str) -> str:
    return "PCR:" + hashlib.sha1(
        input_digest(policy_id, new_hash, requested_by).encode()).hexdigest()[:12]


def change_event_id(change_id_: str, from_status: str, to_status: str) -> str:
    return "PCE:" + hashlib.sha1(
        input_digest(change_id_, from_status, to_status).encode()).hexdigest()[:12]


def approval_id(change_id_: str, approver: str, decision: str) -> str:
    return "PAP:" + hashlib.sha1(
        input_digest(change_id_, approver, decision).encode()).hexdigest()[:12]


def snapshot_id(config_hash: str) -> str:
    return "PSN:" + hashlib.sha1(config_hash.encode()).hexdigest()[:12]


def drift_report_id(snapshot_id_: str, actual_hash: str) -> str:
    return "PDR:" + hashlib.sha1(
        input_digest(snapshot_id_, actual_hash).encode()).hexdigest()[:12]


def configuration_hash(active_policies: list) -> str:
    """현재 활성 정책 집합의 결정적 설정 해시."""
    payload = sorted([(p.get("policy_id"), p.get("version"), p.get("policy_hash"))
                      for p in active_policies])
    return _digest(payload)


def compliance_score(critical_drift: int, warning_drift: int, pending: int) -> int:
    penalty = (critical_drift * _DRIFT_PENALTY[CRITICAL_DRIFT]
               + warning_drift * _DRIFT_PENALTY[WARNING_DRIFT] + pending * 2)
    return max(0, min(100, 100 - penalty))


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class PolicyDefinition:
    policy_id: str
    name: str
    category: str
    version: str
    parameters: dict
    description: str
    created_by: str
    created_at: str
    policy_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyChangeEvent:
    """변경요청 상태전이 이벤트(이벤트 소싱). 현재 상태 = 마지막 to_status."""
    event_id: str
    change_id: str
    policy_id: str
    old_hash: str
    new_hash: str
    reason: str
    requested_by: str
    from_status: str
    to_status: str
    status: str                     # = to_status(편의)
    timestamp: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    change_id: str
    approver: str
    decision: str                   # APPROVE | REJECT
    reason: str
    timestamp: str
    change_hash: str = ""           # 승인 대상 change 의 new_hash(무결성 참조)
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicySnapshot:
    snapshot_id: str
    policy_versions: dict
    configuration_hash: str
    created_at: str
    policy_count: int = 0
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDriftReport:
    report_id: str
    snapshot_id: str
    expected_hash: str
    actual_hash: str
    drift_detected: bool
    drift_level: str                # NO_DRIFT | WARNING_DRIFT | CRITICAL_DRIFT
    findings: list
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyGovernanceReport:
    timestamp: str
    policy_count: int
    active_versions: dict
    pending_changes: int
    approved_changes: int
    drift_count: int
    compliance_score: int

    def to_dict(self) -> dict:
        return asdict(self)
