"""Execution Risk 자료형 (P8.5) — 브로커 제출 직전 '최종' 리스크 집행검사. **집행 아님.**

이미 승인된 집행요청이 '여전히' 안전한지 결정론적으로 평가만 → ALLOW/BLOCK.
**주문 생성 없음·주문 제출 없음·집행 게이트웨이 import 없음.** 읽기전용·재현가능·해시체인.
하나라도 FAILED → 반드시 BLOCK.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

ALLOW = "ALLOW"
BLOCK = "BLOCK"

CRITICAL = "CRITICAL"
WARN = "WARNING"
INFO = "INFO"

GENESIS = "GENESIS"

_EPS = 1e-12


@dataclass(frozen=True)
class RiskCheck:
    name: str
    status: str               # PASS | WARNING | FAILED
    severity: str             # CRITICAL | WARNING | INFO
    value: float | bool | None = None
    limit: float | bool | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionRiskReport:
    report_id: str
    request_id: str
    timestamp: str
    overall_status: str       # ALLOW | BLOCK
    individual_checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    blocker_reason: str = ""
    input_hash: str = ""
    report_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def severity_for(status: str) -> str:
    if status == FAILED:
        return CRITICAL
    if status == WARNING:
        return WARN
    return INFO


def report_id(request_id: str, input_hash_: str) -> str:
    return "XRR:" + hashlib.sha1(f"{request_id}|{input_hash_}".encode()).hexdigest()[:12]


def input_hash(request_id: str, context: dict, policy: dict) -> str:
    blob = json.dumps({"request_id": request_id, "context": context, "policy": policy},
                      sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def report_hash(report_id_: str, request_id: str, overall_status: str, checks: list,
                failures: list, warnings: list, input_hash_: str) -> str:
    payload = {"report_id": report_id_, "request_id": request_id,
               "overall_status": overall_status,
               "checks": [(c["name"], c["status"]) for c in checks],
               "failures": sorted(failures), "warnings": sorted(warnings),
               "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
