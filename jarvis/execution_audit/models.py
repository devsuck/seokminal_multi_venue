"""Execution Audit 자료형 (P8.6) — 집행 파이프라인 교차검증 '증명'만. **집행 아님.**

Request(P8.1)+Lifecycle(P8.2)+Reconciliation(P8.3)+Cost(P8.4)+Risk(P8.5) →
ExecutionAuditCertificate. 이 인증서는 "모든 것이 내부적으로 일관됨"만 진술.
**거래를 승인하지 않는다.** 읽기전용·결정적·재현가능·해시체인.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

GENESIS = "GENESIS"

_ORDER = {PASS: 0, WARNING: 1, FAILED: 2}


@dataclass(frozen=True)
class AuditCheck:
    name: str
    status: str               # PASS | WARNING | FAILED
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionAuditCertificate:
    certificate_id: str
    timestamp: str
    request_id: str
    audit_status: str         # PASS | WARNING | FAILED
    audit_score: float = 0.0
    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    input_hash: str = ""
    certificate_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


def overall_status(statuses: list) -> str:
    """any FAILED → FAILED, else any WARNING → WARNING, else PASS."""
    worst = PASS
    for s in statuses:
        if _ORDER.get(s, 0) > _ORDER[worst]:
            worst = s
    return worst


def certificate_id(request_id: str, input_hash_: str) -> str:
    return "EAC:" + hashlib.sha1(f"{request_id}|{input_hash_}".encode()).hexdigest()[:12]


def input_hash(request_id: str, refs: dict) -> str:
    blob = json.dumps({"request_id": request_id, "refs": refs},
                      sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def certificate_hash(certificate_id_: str, request_id: str, audit_status: str,
                     audit_score: float, checks: list, input_hash_: str) -> str:
    payload = {"certificate_id": certificate_id_, "request_id": request_id,
               "audit_status": audit_status, "audit_score": audit_score,
               "checks": [(c["name"], c["status"]) for c in checks],
               "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
