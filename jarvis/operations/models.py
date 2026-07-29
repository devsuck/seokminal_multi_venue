"""Operations Alerting & Incident 자료형 (P9.2) — 관제 레코드만. **집행 아님.**

P9.1 헬스 리포트를 관측 → Alert(INFO/WARNING/ERROR/CRITICAL) → 지속 시 Incident(상태머신) →
CRITICAL 지속 시 Escalation(레코드만, 실제 발송 없음) → Operator Acknowledgement → Resolution.
**상태 변경 없음·거래 인가 없음·브로커 접촉 없음·킬스위치 조작 없음.** 결정적·append-only·해시체인.

각 레코드는 (previous_hash, record_hash) 로 체인된다. record_hash = 콘텐츠(두 해시 필드 제외)의
sha256. 헬스와 달리 타임스탬프는 레코드 정체성의 일부라 해시에 포함(결정적: 동일 입력→동일 해시).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Alert Severity ──
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
CRITICAL = "CRITICAL"

_SEV_ORDER = {INFO: 0, WARNING: 1, ERROR: 2, CRITICAL: 3}

# P9.1 헬스 상태 → Alert Severity (HEALTHY/DEGRADED = _OK → 알림 없음)
_STATUS_TO_SEVERITY = {
    "WARNING": WARNING,
    "CRITICAL": CRITICAL,
    "OFFLINE": ERROR,
    "UNKNOWN": INFO,
}

# Incident 를 생성할 수 있는(지속 추적 대상) severity — INFO 는 인시던트 없음
_INCIDENT_SEVERITIES = {WARNING, ERROR, CRITICAL}

# ── Incident 상태머신 ──
OPEN = "OPEN"
ACKNOWLEDGED = "ACKNOWLEDGED"
MITIGATING = "MITIGATING"
RESOLVED = "RESOLVED"
CLOSED = "CLOSED"

INCIDENT_STATES = (OPEN, ACKNOWLEDGED, MITIGATING, RESOLVED, CLOSED)

# 허용 전이 — 그 외 전이는 모두 차단
ALLOWED_TRANSITIONS = {
    "": {OPEN},                       # 생성(genesis) → OPEN
    OPEN: {ACKNOWLEDGED, MITIGATING},
    ACKNOWLEDGED: {MITIGATING, RESOLVED},
    MITIGATING: {RESOLVED},
    RESOLVED: {CLOSED},
    CLOSED: set(),                    # 종료 상태(불변)
}

# 활성(추가 인시던트 dedup 대상) — 종료되지 않은 상태
_ACTIVE_INCIDENT_STATES = {OPEN, ACKNOWLEDGED, MITIGATING}


class IllegalTransition(Exception):
    """차단된 인시던트 상태 전이."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def severity_of_status(status: str) -> str | None:
    """헬스 상태 → Alert severity. 알림 불필요(HEALTHY/DEGRADED 등)면 None."""
    return _STATUS_TO_SEVERITY.get(status)


def severity_rank(sev: str) -> int:
    return _SEV_ORDER.get(sev, 0)


def is_incident_severity(sev: str) -> bool:
    return sev in _INCIDENT_SEVERITIES


def is_active_state(state: str) -> bool:
    return state in _ACTIVE_INCIDENT_STATES


# ── 해시(콘텐츠 결정적) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    """의미 입력들의 결정적 다이제스트(레코드 id 파생용)."""
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    """레코드 콘텐츠(두 해시 필드 제외)의 결정적 해시 — 변조 탐지 기준."""
    core = {k: v for k, v in record.items() if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def alert_id(source: str, severity: str, report_id: str, timestamp: str) -> str:
    return "ALT:" + hashlib.sha1(
        input_digest(source, severity, report_id, timestamp).encode()).hexdigest()[:12]


def alert_key(source: str, severity: str) -> str:
    """지속성 추적/dedup 그룹 키 — 시간 무관(동일 원인 그룹)."""
    return f"{source}|{severity}"


def incident_id(a_key: str, first_seen: str) -> str:
    return "INC:" + hashlib.sha1(input_digest(a_key, first_seen).encode()).hexdigest()[:12]


def incident_event_id(incident_id_: str, from_state: str, to_state: str, at: str) -> str:
    """인시던트는 이벤트 소싱 — 각 전이 이벤트가 고유 primary id 를 가진다(중복 탐지용)."""
    return "IEV:" + hashlib.sha1(
        input_digest(incident_id_, from_state, to_state, at).encode()).hexdigest()[:12]


def escalation_id(incident_id_: str, level: int, at: str) -> str:
    return "ESC:" + hashlib.sha1(
        input_digest(incident_id_, level, at).encode()).hexdigest()[:12]


def ack_id(incident_id_: str, operator: str, at: str) -> str:
    return "ACK:" + hashlib.sha1(
        input_digest(incident_id_, operator, at).encode()).hexdigest()[:12]


def resolution_id(incident_id_: str, at: str) -> str:
    return "RES:" + hashlib.sha1(input_digest(incident_id_, at).encode()).hexdigest()[:12]


# ── 레코드 자료형(모두 frozen·순수 데이터) ──
@dataclass(frozen=True)
class Alert:
    alert_id: str
    timestamp: str
    source: str                     # 서브시스템 이름 또는 "system"
    severity: str                   # INFO | WARNING | ERROR | CRITICAL
    health_status: str              # 관측된 P9.1 상태
    alert_key: str
    report_id: str                  # 근거가 된 P9.1 리포트
    message: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IncidentEvent:
    event_id: str                   # 이벤트별 고유 primary id
    incident_id: str                # 인시던트 그룹 id(이벤트 간 공유)
    timestamp: str
    alert_key: str
    severity: str
    from_state: str
    to_state: str
    reason: str = ""
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Escalation:
    escalation_id: str
    timestamp: str
    incident_id: str
    alert_key: str
    severity: str
    level: int
    duration_seconds: float
    reason: str = ""
    channels_notified: list = field(default_factory=list)   # 항상 빈 목록 — 실제 발송 없음
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Acknowledgement:
    ack_id: str
    timestamp: str
    incident_id: str
    operator: str
    note: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Resolution:
    resolution_id: str
    timestamp: str
    incident_id: str
    resolved_by: str
    resolution: str = ""            # 종료 분류(예: fixed / auto_recovered / false_positive)
    note: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


def fold_incident_state(events: list) -> str:
    """인시던트 이벤트 목록 → 현재 상태(마지막 to_state). 없으면 ''."""
    if not events:
        return ""
    return events[-1].get("to_state", "")
