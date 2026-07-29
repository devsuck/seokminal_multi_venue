"""Meta Research Intelligence 자료형 (P30) — 연구 과정 자체의 연구. **관찰 전용, 동작 없음.**

연구 과정 자체를 연구한다: 연구 효율·검증 품질·실패 빈도·연구 속도·지식 재사용 분석. Meta Metrics·Meta Reports·
Research Quality Records·Optimization Opportunities·Meta Lineage 를 소유한다. **자동 최적화 없음 — 관찰만.**
OBSERVATION ≠ OPTIMIZATION · META ≠ EXECUTION · OPPORTUNITY ≠ APPLIED. 불변·append-only·SHA256 해시체인·결정적.
물리 원장 mri_ 접두사. 상위 계층(P10~P29)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 메타 지표 이름(연구 과정 5개 차원) ──
META_METRIC_NAMES = ("research_efficiency", "validation_quality", "failure_frequency",
                     "research_velocity", "knowledge_reuse")
# ── 품질 차원 ──
QUALITY_DIMENSIONS = ("VALIDATION", "REPRODUCIBILITY", "EVIDENCE", "NOVELTY", "RIGOR")
# ── 최적화 기회 영역 ──
OPPORTUNITY_AREAS = ("EFFICIENCY", "VALIDATION", "VELOCITY", "REUSE", "RELIABILITY")
# ── 메타 관찰 측면 ──
OBSERVATION_ASPECTS = ("PROCESS", "QUALITY", "FAILURE", "VELOCITY", "REUSE")

# ── 아티팩트 유형 ──
ART_METRIC = "META_METRIC"
ART_QUALITY = "QUALITY"
ART_OPPORTUNITY = "OPPORTUNITY"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·최적화·거래·승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "AUTO_OPTIMIZE", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
    "OPTIMIZE", "APPLY_OPTIMIZATION", "SELECT", "PROMOTE",
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


# ── 결정적 ID (MT* 스킴) ──
def metric_id(metric_name, seq) -> str:
    return _id("MTM", metric_name, seq)


def quality_id(subject, dimension) -> str:
    return _id("MTQ", subject, dimension)


def opportunity_id(area, description) -> str:
    return _id("MTO", area, description)


def observation_id(aspect, finding) -> str:
    return _id("MTB", aspect, finding)


def report_id(scope, created_at) -> str:
    return _id("MTR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("MTA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


def ratio(numerator, denominator) -> float:
    d = float(denominator)
    if d == 0.0:
        return 0.0
    return round(float(numerator) / d, 6)


def classify_quality(score) -> str:
    """품질 점수(0..1) → 등급(결정적, 관찰용)."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "LOW"
    if s >= 0.8:
        return "HIGH"
    if s >= 0.5:
        return "MEDIUM"
    return "LOW"


def opportunity_priority(evidence_count) -> float:
    """기회 우선순위 점수(0..1, 결정적). **점수만 — 자동 적용 없음.**"""
    try:
        n = max(0, int(evidence_count))
    except (TypeError, ValueError):
        return 0.0
    return round(1.0 - 1.0 / (1.0 + n), 6)


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
class MetaMetricRecord:
    metric_id: str
    metric_name: str
    value: float
    unit: str
    dimension: str
    source_reference: str
    is_observation: bool  # 항상 True — 관찰만, 자동 최적화 없음
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QualityRecord:
    quality_id: str
    subject: str
    dimension: str
    score: float
    grade: str
    assessment: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OptimizationOpportunityRecord:
    opportunity_id: str
    area: str
    description: str
    evidence: dict
    priority_score: float
    is_applied: bool  # 항상 False — 기록만, 자동 적용/최적화 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetaObservationRecord:
    observation_id: str
    aspect: str
    finding: str
    evidence: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetaReportRecord:
    report_id: str
    scope: str
    metric_count: int
    quality_count: int
    opportunity_count: int
    observation_count: int
    meta_metrics: dict
    quality_distribution: dict
    area_distribution: dict
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
class MetaSummary:
    timestamp: str
    metric_count: int
    quality_count: int
    opportunity_count: int
    observation_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
