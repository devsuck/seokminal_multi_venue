"""Access Governance & Operator Identity 자료형 (P9.10) — 신원 거버넌스·접근 감사 전용.

**실제 권한 부여 없음·permission 변경 없음·operator action 실행 없음.** 운영자/역할/세션/접근요청/
승인/감사 기록만. 불변·append-only 해시체인·결정적. record_hash = 정렬 canonical json sha256(체인
필드 제외). 물리 원장은 ag_ 접두사(기존 approvals 원장과 충돌 회피). 기존 permission 시스템 READ ONLY.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Access Request 상태머신 ──
REQUESTED = "REQUESTED"
REVIEWED = "REVIEWED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"

ACCESS_STATES = (REQUESTED, REVIEWED, APPROVED, REJECTED, EXPIRED)

ALLOWED_TRANSITIONS = {
    "": {REQUESTED},
    REQUESTED: {REVIEWED},
    REVIEWED: {APPROVED, REJECTED},
    APPROVED: {EXPIRED},
    REJECTED: set(),
    EXPIRED: set(),
}
_PENDING = {REQUESTED, REVIEWED}

# ── 세션 상태 ──
ACTIVE = "ACTIVE"
SESSION_EXPIRED = "EXPIRED"

# ── 승인 결정 ──
APPROVE = "APPROVE"
REJECT = "REJECT"
_DECISIONS = {APPROVE, REJECT}

# ── Finding severity ──
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

_PENALTY = {CRITICAL: 34, WARNING: 8, INFO: 2}
_SEV_RANK = {INFO: 1, WARNING: 2, CRITICAL: 3}


class IllegalTransition(Exception):
    """차단된 접근요청 상태 전이."""


class ImmutableOperatorError(Exception):
    """불변 운영자 신원 위반."""


class ImmutableRoleError(Exception):
    """불변 역할 메타 위반."""


class ApprovalError(Exception):
    """승인 거버넌스 위반."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def is_valid_decision(d: str) -> bool:
    return d in _DECISIONS


def is_pending(status: str) -> bool:
    return status in _PENDING


def severity_rank(sev: str) -> int:
    return _SEV_RANK.get(sev, 0)


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


def identity_hash(operator_id: str, name: str, email: str, roles: list) -> str:
    return _digest({"operator_id": operator_id, "name": name, "email": email,
                    "roles": sorted(roles or [])})


def role_hash(role_id: str, name: str, description: str, scope: list) -> str:
    return _digest({"role_id": role_id, "name": name, "description": description,
                    "scope": sorted(scope or [])})


def session_id(operator_id: str, started_at: str) -> str:
    return "SES:" + hashlib.sha1(input_digest(operator_id, started_at).encode()).hexdigest()[:12]


def access_request_id(operator_id: str, resource: str, requested_scope: str) -> str:
    return "ACR:" + hashlib.sha1(
        input_digest(operator_id, resource, requested_scope).encode()).hexdigest()[:12]


def access_event_id(request_id: str, from_state: str, to_state: str) -> str:
    return "ACE:" + hashlib.sha1(
        input_digest(request_id, from_state, to_state).encode()).hexdigest()[:12]


def approval_id(request_id: str, approver: str, decision: str) -> str:
    return "AAP:" + hashlib.sha1(
        input_digest(request_id, approver, decision).encode()).hexdigest()[:12]


def audit_report_id(input_hash_: str) -> str:
    return "AAR:" + hashlib.sha1(input_hash_.encode()).hexdigest()[:12]


def compliance_score(critical: int, warning: int, info: int) -> int:
    penalty = critical * _PENALTY[CRITICAL] + warning * _PENALTY[WARNING] + info * _PENALTY[INFO]
    return max(0, min(100, 100 - penalty))


def parse_ts(ts: str):
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def session_status(expires_at: str, now: str) -> str:
    ea, nt = parse_ts(expires_at), parse_ts(now)
    if ea and nt and nt > ea:
        return SESSION_EXPIRED
    return ACTIVE


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class OperatorIdentity:
    operator_id: str
    name: str
    email: str
    roles: list
    status: str
    created_at: str
    identity_hash: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RoleMetadata:
    role_hash: str
    role_id: str
    name: str
    description: str
    scope: list                     # 서술적 권한 범위(감사용 메타 — 실제 권한 부여 아님)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    operator_id: str
    started_at: str
    expires_at: str
    status: str
    context: dict = field(default_factory=dict)
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AccessRequest:
    """접근요청 상태전이 이벤트(이벤트 소싱). 현재 상태 = 마지막 to_state."""
    event_id: str
    request_id: str
    operator_id: str
    resource: str
    requested_scope: str
    reason: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AccessApproval:
    approval_id: str
    request_id: str
    approver: str
    decision: str
    reason: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AccessFinding:
    finding_id: str
    severity: str
    rule: str
    subject: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def sort_key(self) -> tuple:
        return (-severity_rank(self.severity), self.rule, self.subject)


@dataclass(frozen=True)
class AccessAuditReport:
    report_id: str
    timestamp: str
    checks: dict
    findings: list
    critical_findings: int
    warning_findings: int
    info_findings: int
    compliance_score: int
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AccessGovernanceReport:
    timestamp: str
    operator_count: int
    role_count: int
    session_count: int
    active_sessions: int
    request_state_distribution: dict
    pending_requests: int
    approved_requests: int

    def to_dict(self) -> dict:
        return asdict(self)


def finding(rule: str, subject: str, severity: str, detail: str = "") -> AccessFinding:
    fid = "AFN:" + hashlib.sha1(input_digest(rule, subject).encode()).hexdigest()[:12]
    return AccessFinding(finding_id=fid, severity=severity, rule=rule, subject=subject,
                         detail=detail)
