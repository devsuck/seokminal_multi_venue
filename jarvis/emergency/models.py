"""Emergency Response 자료형 (P9.3) — 비상 결정 레코드만. **집행 아님·킬스위치 작동 아님.**

P9.1 헬스·P8.5 리스크·P9.2 인시던트/에스컬레이션을 관측 → EmergencyDecision(비상 상태 판정).
Recovery 는 자동 금지 — Operator 승인 모델(Request/Approval/Decision)만 제공. **Gateway/Broker/
Order Cancel/실제 Kill Switch 작동 없음.** 오직 결정 레코드 생성. 결정적·append-only·해시체인.

각 레코드는 (previous_hash, record_hash) 로 체인. record_hash = 콘텐츠(두 해시필드 제외) sha256.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Emergency States ──
NORMAL = "NORMAL"
WATCH = "WATCH"
SAFE_MODE = "SAFE_MODE"
KILL_PENDING = "KILL_PENDING"
KILL_ACTIVE = "KILL_ACTIVE"
RECOVERY_PENDING = "RECOVERY_PENDING"
RECOVERED = "RECOVERED"

EMERGENCY_STATES = (NORMAL, WATCH, SAFE_MODE, KILL_PENDING, KILL_ACTIVE,
                    RECOVERY_PENDING, RECOVERED)

# 심각도 순위(감사/집계용)
_STATE_RANK = {NORMAL: 0, WATCH: 1, SAFE_MODE: 2, KILL_PENDING: 3, KILL_ACTIVE: 4,
               RECOVERY_PENDING: 3, RECOVERED: 1}

# KILL_ACTIVE 는 래치 상태 — 자동 하향 불가(Operator 복구만)
_LATCHED = {KILL_ACTIVE}

# ── 참조 상수(외부 계층 import 없이 문자열 비교만) ──
# P9.1 헬스 상태
H_HEALTHY, H_DEGRADED, H_WARNING = "HEALTHY", "DEGRADED", "WARNING"
H_CRITICAL, H_OFFLINE, H_UNKNOWN = "CRITICAL", "OFFLINE", "UNKNOWN"
# P8.5 리스크 판정
R_ALLOW, R_BLOCK = "ALLOW", "BLOCK"
# P9.2 인시던트 활성 상태 / 심각도
_ACTIVE_INCIDENT = {"OPEN", "ACKNOWLEDGED", "MITIGATING"}
INC_CRITICAL = "CRITICAL"


class RecoveryNotPermitted(Exception):
    """복구 흐름 위반(현재 상태에서 허용되지 않는 복구 조작)."""


# ── 해시(콘텐츠 결정적) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items() if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def decision_id(input_hash_: str, now: str, source: str) -> str:
    return "EMG:" + hashlib.sha1(
        input_digest(input_hash_, now, source).encode()).hexdigest()[:12]


def recovery_request_id(operator: str, now: str) -> str:
    return "RCVQ:" + hashlib.sha1(input_digest(operator, now).encode()).hexdigest()[:12]


def recovery_approval_id(request_id: str, approver: str, now: str) -> str:
    return "RCVA:" + hashlib.sha1(
        input_digest(request_id, approver, now).encode()).hexdigest()[:12]


def recovery_event_id(request_id: str, from_state: str, to_state: str, now: str) -> str:
    return "RCVE:" + hashlib.sha1(
        input_digest(request_id, from_state, to_state, now).encode()).hexdigest()[:12]


def state_rank(state: str) -> int:
    return _STATE_RANK.get(state, 0)


def is_latched(state: str) -> bool:
    return state in _LATCHED


# ── 비상 상태 판정(결정적) ──
def grade(health_status: str, risk_status: str, risk_warn_count: int,
          critical_incident: bool, warning_incident: bool,
          escalation_active: bool) -> tuple[str, list]:
    """관측 입력 → 비상 상태 + 사유. **결정적·순수함수.**

    규칙(우선순위 높은 순):
      1. KILL_ACTIVE  : Health CRITICAL & Risk BLOCK & CRITICAL Incident (세 조건 모두)
      2. KILL_PENDING : 위 세 심각신호 중 2개 이상, 또는 활성 에스컬레이션
      3. SAFE_MODE    : 심각신호 1개, 또는 Health OFFLINE, 또는 (Health WARNING & Risk WARNING),
                        또는 활성 WARNING/ERROR 인시던트
      4. WATCH        : Health WARNING/DEGRADED/UNKNOWN, 또는 Risk WARNING
      5. NORMAL       : 그 외
    """
    hc = health_status == H_CRITICAL
    ho = health_status == H_OFFLINE
    hw = health_status == H_WARNING
    hdu = health_status in (H_DEGRADED, H_UNKNOWN)
    rb = risk_status == R_BLOCK
    rw = risk_warn_count > 0

    reasons: list = []
    severe = sum([hc, rb, critical_incident])

    if hc and rb and critical_incident:
        return KILL_ACTIVE, ["health_critical", "risk_block", "critical_incident"]

    if severe >= 2 or escalation_active:
        if hc:
            reasons.append("health_critical")
        if rb:
            reasons.append("risk_block")
        if critical_incident:
            reasons.append("critical_incident")
        if escalation_active:
            reasons.append("escalation_active")
        return KILL_PENDING, reasons

    if severe == 1 or ho or (hw and rw) or warning_incident:
        if hc:
            reasons.append("health_critical")
        if rb:
            reasons.append("risk_block")
        if critical_incident:
            reasons.append("critical_incident")
        if ho:
            reasons.append("health_offline")
        if hw and rw:
            reasons.append("warning_accumulation")
        if warning_incident:
            reasons.append("warning_incident")
        return SAFE_MODE, reasons

    if hw or hdu or rw:
        if hw:
            reasons.append("health_warning")
        if hdu:
            reasons.append("health_degraded")
        if rw:
            reasons.append("risk_warning")
        return WATCH, reasons

    return NORMAL, []


def reconcile(current: str, graded: str) -> str:
    """현재 상태와 판정을 조정(래치 규칙). **자동 복구 금지.**

    KILL_ACTIVE=래치(Operator 복구만) · RECOVERY_PENDING=복구 흐름만 변경 ·
    RECOVERED=래치 해제 후 판정 재개 · 그 외=판정 추종.
    """
    if current == KILL_ACTIVE:
        return KILL_ACTIVE
    if current == RECOVERY_PENDING:
        return RECOVERY_PENDING
    if current == RECOVERED:
        return graded
    return graded


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class EmergencyDecision:
    decision_id: str
    timestamp: str
    emergency_state: str
    previous_state: str
    source: str                     # "assess" | "recovery_request" | "recovery_approval"
    health_status: str = ""
    risk_status: str = ""
    critical_incident: bool = False
    escalation_active: bool = False
    reasons: list = field(default_factory=list)
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryRequest:
    request_id: str
    timestamp: str
    requested_by: str
    from_state: str
    reason: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryApproval:
    approval_id: str
    timestamp: str
    request_id: str
    approver: str
    approved: bool
    note: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryEvent:
    """RecoveryDecision — 복구의 실제 상태 전이 결과 레코드."""
    event_id: str
    timestamp: str
    request_id: str
    from_state: str
    to_state: str
    outcome: str                    # "approved" | "rejected"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


def fold_active_incidents(incident_rows: list) -> tuple[bool, bool, set]:
    """P9.2 인시던트 이벤트 행 → (critical_active, warning_active, active_ids).

    incident_id 별 마지막 이벤트의 to_state/severity 로 판정. 활성=OPEN/ACK/MITIGATING.
    """
    latest: dict = {}
    for r in incident_rows or []:
        latest[r.get("incident_id")] = r
    critical = False
    warning = False
    active_ids: set = set()
    for inc_id, r in latest.items():
        if r.get("to_state") in _ACTIVE_INCIDENT:
            active_ids.add(inc_id)
            if r.get("severity") == INC_CRITICAL:
                critical = True
            else:
                warning = True
    return critical, warning, active_ids
