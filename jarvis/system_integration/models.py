"""System Integration & Final Validation 자료형 (P35) — 전체 연구 생태계 검증. **통합 전용, 기능 추가 없음.**

전체 연구 생태계를 검증한다: 계층 간 무결성·소유권 검증·원장 검증·해시 검증·계보 검증·결정적 재현·API 일관성·안전성 검증.
시스템 리포트·커버리지 리포트·의존성 그래프·아키텍처 요약을 생성한다. **기능 추가 없음 — 통합·검증만.** 계층 소유권/원장은
불변, READ ONLY(정적 검사·파일 읽기만, import 결합 없음). VALIDATION ≠ MUTATION · INTEGRATION ≠ EXECUTION.
물리 원장 sysint_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 검증 대상 계층 레지스트리(P21~P34) — package·prefix·phase ──
LAYER_REGISTRY = (
    {"package": "production_readiness", "prefix": "pd_", "phase": "P21"},
    {"package": "research_automation", "prefix": "ra_", "phase": "P22"},
    {"package": "research_monitoring", "prefix": "rmon_", "phase": "P23"},
    {"package": "research_reliability", "prefix": "rel_", "phase": "P24"},
    {"package": "autonomous_research", "prefix": "ar_", "phase": "P25"},
    {"package": "research_agent_coordination", "prefix": "racd_", "phase": "P26"},
    {"package": "research_memory_intelligence", "prefix": "rmi_", "phase": "P27"},
    {"package": "research_insight_intelligence", "prefix": "rii_", "phase": "P28"},
    {"package": "research_strategy_generation", "prefix": "rsg_", "phase": "P29"},
    {"package": "meta_research_intelligence", "prefix": "mri_", "phase": "P30"},
    {"package": "experiment_orchestration", "prefix": "exo_", "phase": "P31"},
    {"package": "research_resource_manager", "prefix": "rrm_", "phase": "P32"},
    {"package": "research_api_gateway", "prefix": "rgw_", "phase": "P33"},
    {"package": "research_dashboard_backend", "prefix": "rdb_", "phase": "P34"},
)

REQUIRED_MODULES = ("__init__.py", "models.py", "ledger.py", "engine.py", "verify.py",
                    "__main__.py")

# ── 검증 유형 ──
CHECK_TYPES = ("STRUCTURE", "OWNERSHIP", "PREFIX_CONFINEMENT", "SAFETY_IMPORTS", "SAFETY_METHODS",
               "APPEND_ONLY", "MODEL_LEAK", "HASH_CHAIN", "LINEAGE", "API_CONSISTENCY")
# ── 검증 상태 ──
CHECK_STATUSES = ("PASS", "FAIL")

# ── 안전성 스캔 상수(모든 계층 공통) ──
# 모델 식별자 유출 스캔 토큰 — 리터럴이 소스에 나타나지 않도록 분리 구성(자체 스캔 오탐 방지).
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
FORBIDDEN_IMPORT_PREFIXES = ("jarvis.execution", "jarvis.broker", "jarvis.live_trading",
                             "jarvis.portfolio_execution", "jarvis.live_portfolio")
FORBIDDEN_METHOD_NAMES = frozenset({
    "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "activate_live",
    "approve_for_trading", "execute", "deploy", "trade", "run_experiment", "execute_experiment",
})

# ── 아티팩트 유형 ──
ART_VALIDATION = "VALIDATION"
ART_REPORT = "REPORT"

# ── 절대 금지 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "MUTATE_LEDGER",
    "MODIFY_OWNERSHIP", "PROMOTE",
})


# ── 해시(SHA256) — 모든 계층과 동일 알고리즘(범용 검증용) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    """모든 계층과 동일: previous_hash/record_hash/report_hash 제외 core 의 SHA256."""
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def value_hash(*parts) -> str:
    return _digest(list(parts))


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (SI* 스킴) ──
def validation_id(scope, created_at) -> str:
    return _id("SIV", scope, created_at)


def finding_id(layer, check_type, seq) -> str:
    return _id("SIF", layer, check_type, seq)


def report_id(scope, created_at) -> str:
    return _id("SIR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("SIA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def registered_prefixes() -> list:
    return [layer["prefix"] for layer in LAYER_REGISTRY]


def registered_packages() -> list:
    return [layer["package"] for layer in LAYER_REGISTRY]


def prefixes_unique() -> bool:
    pfx = registered_prefixes()
    return len(pfx) == len(set(pfx))


def packages_unique() -> bool:
    pkg = registered_packages()
    return len(pkg) == len(set(pkg))


def verify_hash_records(records) -> dict:
    """범용 해시체인 검증(모든 계층 공통 알고리즘). previous_hash 링크 + record_hash 재계산 + id 중복 없음."""
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


def detect_cycle_check(edges) -> bool:
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}

    def dfs(node) -> bool:
        color[node] = GRAY
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(nxt):
                return True
        color[node] = BLACK
        return False

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE and dfs(node):
            return True
    return False


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ValidationRecord:
    validation_id: str
    scope: str
    checks_run: int
    checks_passed: int
    checks_failed: int
    all_passed: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FindingRecord:
    finding_id: str
    layer: str
    check_type: str
    status: str
    detail: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SystemReportRecord:
    report_id: str
    scope: str
    layer_count: int
    validation_count: int
    finding_count: int
    failed_finding_count: int
    check_type_distribution: dict
    architecture_summary: dict
    dependency_graph: dict
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
class IntegrationSummary:
    timestamp: str
    layer_count: int
    validation_count: int
    finding_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
