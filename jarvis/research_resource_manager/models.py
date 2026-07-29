"""Research Resource Manager 자료형 (P32) — 연구 자원 추적 기록 전용. **자동 배분·프로비저닝 없음.**

연구 자원을 추적한다: 데이터셋·컴퓨트·스토리지·연구 예산·GPU 사용·실험 배분. **기록만 한다 — 자동으로 배분하지 않으며
인프라를 프로비저닝하지 않는다.** RECORD ≠ ALLOCATE · RECORD ≠ PROVISION · TRACK ≠ EXECUTE. 불변·append-only·
SHA256 해시체인·결정적. 물리 원장 rrm_ 접두사. 상위 계층(P10~P31)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 자원 유형 ──
RESOURCE_TYPES = ("DATASET", "COMPUTE", "STORAGE", "GPU", "BUDGET")
# ── 사용 목적 ──
USAGE_PURPOSES = ("EXPERIMENT", "BACKTEST", "SIMULATION", "TRAINING", "ANALYSIS")
# ── 예산 카테고리 ──
BUDGET_CATEGORIES = ("COMPUTE", "STORAGE", "DATA", "TOOLING", "GENERAL")

# ── 아티팩트 유형 ──
ART_RESOURCE = "RESOURCE"
ART_BUDGET = "BUDGET"
ART_ALLOCATION = "ALLOCATION"
ART_REPORT = "REPORT"

# ── 절대 금지(자동 배분·프로비저닝·실행·거래) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "PROVISION", "AUTO_ALLOCATE", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "PROVISION_INFRA",
    "AUTO_PROVISION", "SPIN_UP", "LAUNCH_INSTANCE",
})


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


# ── 해시(SHA256) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


def value_hash(*parts) -> str:
    return _digest(list(parts))


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (RS* 스킴) ──
def resource_id(resource_type, name) -> str:
    return _id("RSR", resource_type, name)


def usage_id(resource, seq) -> str:
    return _id("RSU", resource, seq)


def budget_id(category, period) -> str:
    return _id("RSB", category, period)


def allocation_id(resource, experiment_ref, seq) -> str:
    return _id("RSL", resource, experiment_ref, seq)


def report_id(scope, created_at) -> str:
    return _id("RSO", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("RSA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def ratio(numerator, denominator) -> float:
    d = float(denominator)
    if d == 0.0:
        return 0.0
    return round(float(numerator) / d, 6)


def utilization(used, capacity) -> float:
    """사용률(0..∞, 결정적). capacity 0 이면 0."""
    return ratio(used, capacity)


def classify_utilization(rate) -> str:
    """사용률 → 관찰 라벨(결정적)."""
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if r >= 1.0:
        return "OVER_CAPACITY"
    if r >= 0.8:
        return "HIGH"
    if r >= 0.4:
        return "MODERATE"
    return "LOW"


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
class ResourceRecord:
    resource_id: str
    resource_type: str
    name: str
    capacity: float
    unit: str
    source_reference: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class UsageRecord:
    usage_id: str
    resource_id: str
    amount: float
    unit: str
    purpose: str
    detail: str
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BudgetRecord:
    budget_id: str
    category: str
    amount: float
    currency: str
    period: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AllocationRecord:
    allocation_id: str
    resource_id: str
    experiment_ref: str
    requested_amount: float
    unit: str
    is_provisioned: bool  # 항상 False — 기록만, 인프라 프로비저닝 없음
    is_auto: bool  # 항상 False — 기록만, 자동 배분 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResourceReportRecord:
    report_id: str
    scope: str
    resource_count: int
    usage_count: int
    budget_count: int
    allocation_count: int
    type_distribution: dict
    utilization_by_resource: dict
    budget_by_category: dict
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
class ResourceSummary:
    timestamp: str
    resource_count: int
    usage_count: int
    budget_count: int
    allocation_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
