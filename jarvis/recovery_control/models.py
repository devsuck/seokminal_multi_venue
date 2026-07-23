"""Recovery Operations Control 자료형 (P9.4) — 복구 준비도 평가·증거·체크리스트·증언만.

**자동 복구 아님.** P9.1 헬스·P9.2 인시던트/에스컬레이션·P9.3 비상결정을 *데이터로만* 관측 →
RecoveryEvidence(증거) → RecoveryChecklist(결정적 체크) → RecoveryReadinessReport(READY/WARNING/
FAILED) → RecoveryAttestation(Operator 인간 증언 기록). **서비스 재시작·킬스위치 해제·거래 재개·
브로커/집행/리스크/권한/레지스트리/포트폴리오/페이퍼 변경 없음.** 결정적·append-only·해시체인.

증거/체크리스트 해시는 *상태만*(수집 시각 제외) → 동일 상태면 동일 해시(결정적 재현·중복 방지).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Check 상태 ──
PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

# ── Readiness 종합 ──
READY = "READY"
# (WARNING / FAILED 재사용)

# ── Attestation 결정 ──
APPROVE_RESTART_REVIEW = "APPROVE_RESTART_REVIEW"
REJECT = "REJECT"
_DECISIONS = {APPROVE_RESTART_REVIEW, REJECT}

# ── 참조 상수(외부 계층 import 없이 문자열 비교만) ──
H_CRITICAL, H_OFFLINE, H_WARNING = "CRITICAL", "OFFLINE", "WARNING"
E_KILL_ACTIVE, E_KILL_PENDING, E_SAFE_MODE = "KILL_ACTIVE", "KILL_PENDING", "SAFE_MODE"
E_RECOVERY_PENDING, E_RECOVERED, E_NORMAL = "RECOVERY_PENDING", "RECOVERED", "NORMAL"
_ACTIVE_INCIDENT = {"OPEN", "ACKNOWLEDGED", "MITIGATING"}
INC_CRITICAL = "CRITICAL"


class RecoveryAttestationError(Exception):
    """증언 흐름 위반(예: 체크리스트 없이 승인, FAILED 상태에서 승인)."""


# ── 해시 ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    """레코드 콘텐츠(체인/파생 해시 필드 제외) 해시 — 체인/변조 탐지. previous_hash·record_hash·
    report_hash 는 제외(report_hash 는 readiness 리포트의 record_hash 별칭 → 순환 방지)."""
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def evidence_hash(observed: dict) -> str:
    """관측 증거(상태만) 해시 — 수집 시각 무관 결정적."""
    return _digest(observed)


def checklist_hash(checks: list) -> str:
    """체크 결과(이름·상태·필수여부 순서 보존) 해시 — 상태만 결정적."""
    payload = [(c.get("name"), c.get("status"), c.get("mandatory")) for c in checks]
    return _digest(payload)


def evidence_id(evidence_hash_: str) -> str:
    return "REV:" + hashlib.sha1(evidence_hash_.encode()).hexdigest()[:12]


def checklist_id(checklist_hash_: str) -> str:
    return "RCL:" + hashlib.sha1(checklist_hash_.encode()).hexdigest()[:12]


def readiness_id(evidence_hash_: str, checklist_hash_: str) -> str:
    return "RRR:" + hashlib.sha1(
        input_digest(evidence_hash_, checklist_hash_).encode()).hexdigest()[:12]


def attestation_id(operator_id: str, incident_id: str, decision: str,
                   checklist_hash_: str) -> str:
    return "RATT:" + hashlib.sha1(
        input_digest(operator_id, incident_id, decision, checklist_hash_).encode()).hexdigest()[:12]


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class RecoveryCheck:
    name: str
    category: str                   # Health | Incident | Emergency | ExecutionBoundary | Audit
    status: str                     # PASS | WARNING | FAILED
    mandatory: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryEvidence:
    evidence_id: str
    timestamp: str
    observed: dict                  # 관측 상태 요약(헬스/인시던트/비상/집행경계/감사)
    sources: list = field(default_factory=list)   # 관측 원장 파일명들
    evidence_hash: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryChecklist:
    checklist_id: str
    timestamp: str
    checks: list = field(default_factory=list)
    checklist_hash: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryReadinessReport:
    report_id: str
    timestamp: str
    overall_status: str             # READY | WARNING | FAILED
    checks: list = field(default_factory=list)
    checklist_hash: str = ""
    evidence_hash: str = ""
    mandatory_failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    emergency_state: str = ""
    input_hash: str = ""
    report_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryAttestation:
    attestation_id: str
    timestamp: str
    operator_id: str
    incident_id: str
    emergency_state: str
    checklist_hash: str
    evidence_hash: str
    decision: str                   # APPROVE_RESTART_REVIEW | REJECT
    readiness_status: str = ""
    reason: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


def is_valid_decision(decision: str) -> bool:
    return decision in _DECISIONS


def overall_readiness(checks: list) -> tuple[str, list, list]:
    """체크 목록 → (종합, 필수실패 목록, 경고 목록). **결정적.**

    필수 체크 하나라도 FAILED → FAILED. 비필수 FAILED 또는 WARNING → WARNING. 전부 PASS → READY.
    """
    mand_fail = [c["name"] for c in checks if c["status"] == FAILED and c["mandatory"]]
    soft_fail = [c["name"] for c in checks if c["status"] == FAILED and not c["mandatory"]]
    warns = [c["name"] for c in checks if c["status"] == WARNING]
    if mand_fail:
        return FAILED, mand_fail, warns
    if soft_fail or warns:
        return WARNING, mand_fail, warns + soft_fail
    return READY, [], []


def fold_active_incidents(incident_rows: list) -> tuple[bool, bool, set]:
    """P9.2 인시던트 이벤트 행 → (critical_active, any_active, active_ids)."""
    latest: dict = {}
    for r in incident_rows or []:
        latest[r.get("incident_id")] = r
    critical = False
    any_active = False
    active_ids: set = set()
    for inc_id, r in latest.items():
        if r.get("to_state") in _ACTIVE_INCIDENT:
            active_ids.add(inc_id)
            any_active = True
            if r.get("severity") == INC_CRITICAL:
                critical = True
    return critical, any_active, active_ids
