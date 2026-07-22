"""Execution Readiness 자료형 (P7.7) — 집행 전 최종 '인증' 경계. **집행 아님.**

모든 통제 레이어(P7.4~P7.6 + 프로덕션/리스크/브로커/시장데이터) 집계 →
ExecutionReadinessCertificate(READY/BLOCKED).
**이 인증서는 거래 허가가 아니다** — "시스템이 프리플라이트 검사를 통과했다"만 진술.
결정적·읽기전용·재현가능. 브로커 주문 없음·게이트웨이 없음·자본 배치 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

READY = "READY"
BLOCKED = "BLOCKED"

# 체크 상태 / 심각도
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

CRITICAL = "CRITICAL"
WARNING = "WARNING"
INFO = "INFO"


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str               # PASS | WARN | FAIL
    severity: str             # CRITICAL | WARNING | INFO
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionReadinessCertificate:
    certificate_id: str
    status: str               # READY | BLOCKED
    checks: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    intent_id: str = ""
    created_at: str = ""
    input_hash: str = ""
    hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def severity_for(status: str) -> str:
    if status == FAIL:
        return CRITICAL
    if status == WARN:
        return WARNING
    return INFO


def certificate_id(intent_id: str, created_at: str) -> str:
    return "CERT:" + hashlib.sha1(f"{intent_id}|{created_at}".encode()).hexdigest()[:12]


def input_hash(intent_id: str, checks: list) -> str:
    payload = {"intent_id": intent_id,
               "checks": [(c["name"], c["status"]) for c in checks]}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def certificate_hash(certificate_id_: str, status: str, checks: list,
                     blockers: list, warnings: list, input_hash_: str) -> str:
    payload = {"certificate_id": certificate_id_, "status": status,
               "checks": [(c["name"], c["status"]) for c in checks],
               "blockers": sorted(blockers), "warnings": sorted(warnings),
               "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
