"""Security Hardening & Audit 자료형 (P38) — 최종 보안 감사. **감사 전용, 실행 권한 없음.**

최종 보안 감사를 수행한다: 원장 보안(해시체인·변조 탐지·재현)·아키텍처 보안(금지 import·권한 경계·소유권 위반)·런타임 보안
(불안전 실행 경로·숨은 배포 능력·우발적 거래 메서드). 보안 감사 리포트·검증 스크립트를 추가한다. **엔진은 execute/trade/
deploy/allocate/approve 를 노출하지 않는다.** AUDIT ≠ EXECUTION · VALIDATION ≠ MUTATION. 물리 원장 secaud_ 접두사.
"""
from __future__ import annotations

import hashlib
import json

from jarvis.system_integration.models import LAYER_REGISTRY

GENESIS = "GENESIS"

# ── 감사 대상: 14개 등록 계층 + 파이널라이제이션 계층 ──
AUDIT_TARGETS = tuple(l["package"] for l in LAYER_REGISTRY) + (
    "system_integration", "architecture_docs", "performance", "security_audit")

# ── 감사 차원 ──
AUDIT_DIMENSIONS = ("LEDGER_SECURITY", "ARCHITECTURE_SECURITY", "RUNTIME_SECURITY")
# ── 검사 상태 ──
AUDIT_STATUSES = ("PASS", "FAIL")

# ── 금지 import 접두사 ──
FORBIDDEN_IMPORT_PREFIXES = ("jarvis.execution", "jarvis.broker", "jarvis.live_trading",
                             "jarvis.portfolio_execution", "jarvis.live_portfolio")
# ── 엔진 미노출 필수 메서드(실행/거래/배포/배분/승인) ──
FORBIDDEN_ENGINE_METHODS = ("execute", "trade", "deploy", "allocate", "approve")
# ── 금지 메서드 정의(불안전 실행/거래/배포) ──
FORBIDDEN_METHOD_NAMES = frozenset({
    "execute", "trade", "deploy", "allocate", "approve", "execute_trade", "place_order",
    "deploy_strategy", "allocate_capital", "activate_live", "approve_for_trading", "provision",
    "spin_up", "launch_instance", "run_experiment", "execute_experiment",
})
# ── 숨은 배포 능력 탐지 ──
DEPLOYMENT_METHOD_NAMES = frozenset({"deploy", "deploy_strategy", "provision", "provision_infra",
                                     "spin_up", "launch_instance", "activate_live"})
# ── 우발적 거래 메서드 탐지 ──
TRADING_METHOD_NAMES = frozenset({"trade", "execute_trade", "place_order", "submit_order",
                                  "send_order", "route_order"})

MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

# ── 아티팩트 유형 ──
ART_AUDIT = "AUDIT"
ART_REPORT = "REPORT"

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "PROMOTE",
})


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def audit_id(scope, created_at) -> str:
    return _id("SCA", scope, created_at)


def finding_id(target, dimension, seq) -> str:
    return _id("SCF", target, dimension, seq)


def report_id(scope, created_at) -> str:
    return _id("SCR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("SCT", atype, ref)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def verify_hash_records(records) -> dict:
    """범용 해시체인 검증(변조 탐지)."""
    if not records:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_record_hash"}
        if content_hash(r) != r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "record_hash_mismatch"}
        prev = r["record_hash"]
    return {"ok": True, "n": len(records), "reason": "chain_intact"}


# ── 레코드 자료형 ──
from dataclasses import asdict, dataclass  # noqa: E402


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    scope: str
    targets: int
    checks_run: int
    checks_passed: int
    checks_failed: int
    all_secure: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SecurityFindingRecord:
    finding_id: str
    target: str
    dimension: str
    check_name: str
    status: str
    detail: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SecurityReportRecord:
    report_id: str
    scope: str
    target_count: int
    audit_count: int
    finding_count: int
    failed_finding_count: int
    dimension_distribution: dict
    is_binding: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditSummary:
    timestamp: str
    target_count: int
    audit_count: int
    finding_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
