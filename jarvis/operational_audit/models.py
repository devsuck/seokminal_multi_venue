"""Operational Audit & Compliance 자료형 (P9.6) — 감사 전용. **운영 제어권 없음.**

P9.1 헬스·P9.2 알림/인시던트·P9.3 비상/복구·P9.4 복구준비도/증언·P9.5 콘솔접근을 *데이터로만*
읽어 AuditEvent·OperatorAction·ConfigurationSnapshot·AuditFinding·ComplianceReport 로 감사한다.
**집행/브로커/주문/킬스위치/복구실행/권한변경 없음.** append-only 해시체인·결정적·재현가능.

record_hash = 콘텐츠(체인/파생 해시필드 제외) sha256 → 변조 탐지.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Finding Severity ──
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

_SEV_RANK = {INFO: 1, WARNING: 2, CRITICAL: 3}

# 컴플라이언스 점수 가중(감점)
_PENALTY = {CRITICAL: 34, WARNING: 8, INFO: 2}


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


def audit_event_id(source_ledger: str, source_id: str) -> str:
    return "AEV:" + hashlib.sha1(
        input_digest(source_ledger, source_id).encode()).hexdigest()[:12]


def operator_action_id(source_ledger: str, source_id: str) -> str:
    return "OAC:" + hashlib.sha1(
        input_digest(source_ledger, source_id).encode()).hexdigest()[:12]


def snapshot_id(input_hash_: str) -> str:
    return "CFG:" + hashlib.sha1(input_hash_.encode()).hexdigest()[:12]


def finding_id(rule: str, subject: str) -> str:
    return "FND:" + hashlib.sha1(input_digest(rule, subject).encode()).hexdigest()[:12]


def report_id(input_hash_: str) -> str:
    return "CMP:" + hashlib.sha1(input_hash_.encode()).hexdigest()[:12]


def compliance_score(critical: int, warning: int, info: int) -> int:
    penalty = critical * _PENALTY[CRITICAL] + warning * _PENALTY[WARNING] + info * _PENALTY[INFO]
    return max(0, min(100, 100 - penalty))


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: str
    category: str                   # 출처 계층(health|operations|emergency|recovery|console)
    event_type: str                 # health_state|alert_created|incident_lifecycle|...
    subject_id: str
    severity: str = ""              # 관측 심각도(원 레코드의 상태/심각도 라벨)
    detail: str = ""
    source_ledger: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OperatorAction:
    action_id: str
    timestamp: str
    operator_id: str
    action: str                     # attestation | recovery_request | recovery_approval
    target_id: str
    decision: str = ""
    source_ledger: str = ""
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConfigurationSnapshot:
    snapshot_id: str
    timestamp: str
    autonomy_level: int
    min_live_level: int
    live_enabled: bool
    forbidden_count: int
    config: dict = field(default_factory=dict)
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditFinding:
    finding_id: str
    severity: str                   # INFO | WARNING | CRITICAL
    rule: str
    subject: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def sort_key(self) -> tuple:
        return (-severity_rank(self.severity), self.rule, self.subject)


@dataclass(frozen=True)
class ComplianceReport:
    report_id: str
    timestamp: str
    audit_period: dict
    event_count: int
    critical_findings: int
    warning_findings: int
    info_findings: int
    chain_status: str               # intact | broken
    compliance_score: int
    findings: list = field(default_factory=list)
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)
