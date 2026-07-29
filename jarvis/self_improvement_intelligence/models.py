"""Research Self-Improvement Intelligence 자료형 (P10.13) — 연구 과정 최적화 분석 전용.

P10.2~P10.12 연구 이력을 **READ ONLY** 로 소비해 워크플로·개선 기회·병목·프로세스 권고·템플릿 진화·
개선 증거를 기록한다. **연구 과정 분석·제안만 수행한다.** research strategy/model/signal 수정·실험 자동
선택·trading 실행·deploy 없음. IMPROVEMENT SUGGESTION ≠ ACTION · RESEARCH RECOMMENDATION ≠ APPROVAL ·
INSIGHT ≠ EXECUTION. 불변·append-only 해시체인·결정적. 물리 원장은 si_ 접두사(sim_ 과 구별).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Opportunity 생명주기 ──
IDENTIFIED = "IDENTIFIED"
ANALYZED = "ANALYZED"
REVIEWED = "REVIEWED"
ARCHIVED = "ARCHIVED"

OPPORTUNITY_STATES = (IDENTIFIED, ANALYZED, REVIEWED, ARCHIVED)
OPPORTUNITY_TRANSITIONS = {
    "": {IDENTIFIED},
    IDENTIFIED: {ANALYZED},
    ANALYZED: {REVIEWED},
    REVIEWED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Recommendation 생명주기 ──
CREATED = "CREATED"
ACCEPTED = "ACCEPTED"
# REVIEWED / ARCHIVED 공유

RECOMMENDATION_STATES = (CREATED, REVIEWED, ACCEPTED, ARCHIVED)
RECOMMENDATION_TRANSITIONS = {
    "": {CREATED},
    CREATED: {REVIEWED},
    REVIEWED: {ACCEPTED, ARCHIVED},
    ACCEPTED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 심각도(서술 라벨) ──
SEV_LOW = "LOW"
SEV_MEDIUM = "MEDIUM"
SEV_HIGH = "HIGH"
SEV_CRITICAL = "CRITICAL"
SEVERITIES = (SEV_LOW, SEV_MEDIUM, SEV_HIGH, SEV_CRITICAL)

# ── 개선 기회 카테고리(예시) ──
MISSING_WALK_FORWARD = "missing_walk_forward_validation"
INSUFFICIENT_STRESS_TESTING = "insufficient_stress_testing"
REPEATED_PARAMETER_OVERFITTING = "repeated_parameter_overfitting"
INCOMPLETE_LINEAGE = "incomplete_lineage"
OPPORTUNITY_CATEGORIES = (MISSING_WALK_FORWARD, INSUFFICIENT_STRESS_TESTING,
                          REPEATED_PARAMETER_OVERFITTING, INCOMPLETE_LINEAGE)

# ── 병목 유형(예시) ──
REPEATED_FAILED_EXPERIMENTS = "repeated_failed_experiments"
DUPLICATED_DATASETS = "duplicated_datasets"
EXCESSIVE_MANUAL_REVIEW = "excessive_manual_review"
BOTTLENECK_TYPES = (REPEATED_FAILED_EXPERIMENTS, DUPLICATED_DATASETS, EXCESSIVE_MANUAL_REVIEW)

# ── 개선 그래프 노드 유형 ──
NODE_WORKFLOW = "WORKFLOW"
NODE_EXPERIMENT = "EXPERIMENT"
NODE_FAILURE = "FAILURE"
NODE_PATTERN = "PATTERN"
NODE_OPPORTUNITY = "OPPORTUNITY"
NODE_RECOMMENDATION = "RECOMMENDATION"
NODE_TEMPLATE = "TEMPLATE"
NODE_TYPES = (NODE_WORKFLOW, NODE_EXPERIMENT, NODE_FAILURE, NODE_PATTERN, NODE_OPPORTUNITY,
              NODE_RECOMMENDATION, NODE_TEMPLATE)

# ── 개선 그래프 엣지 유형 ──
CAUSED_BY = "CAUSED_BY"
IMPROVES = "IMPROVES"
LEARNED_FROM = "LEARNED_FROM"
DERIVED_FROM = "DERIVED_FROM"
SUPPORTED_BY = "SUPPORTED_BY"
EDGE_TYPES = (CAUSED_BY, IMPROVES, LEARNED_FROM, DERIVED_FROM, SUPPORTED_BY)

# ── Improvement Analysis 가중치(합=1.0) ──
IMPROVEMENT_WEIGHTS = {
    "workflow_efficiency": 0.25,
    "validation_completeness": 0.20,
    "research_reproducibility": 0.20,
    "failure_prevention": 0.20,
    "evidence_coverage": 0.15,
}

# ── Improvement confidence 라벨 ──
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# ── Artifact 유형(계보) ──
ART_SOURCE = "SOURCE"
ART_WORKFLOW = "WORKFLOW"
ART_BOTTLENECK = "BOTTLENECK"
ART_OPPORTUNITY = "OPPORTUNITY"
ART_RECOMMENDATION = "RECOMMENDATION"
ART_EVIDENCE = "EVIDENCE"
ART_REPORT = "REPORT"
ART_TEMPLATE = "TEMPLATE"
ART_EDGE = "IMPROVEMENT_EDGE"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableWorkflowError(Exception):
    """불변 워크플로 위반."""


class ImmutableOpportunityError(Exception):
    """불변 개선 기회 위반."""


class ImmutableBottleneckError(Exception):
    """불변 병목 위반."""


class ImmutableTemplateError(Exception):
    """불변 템플릿 위반."""


class UnknownWorkflow(Exception):
    """미등록 워크플로 참조."""


class UnknownOpportunity(Exception):
    """미등록 개선 기회 참조."""


class UnknownRecommendation(Exception):
    """미등록 권고 참조."""


class InvalidImprovementLink(Exception):
    """유효하지 않은 개선 그래프 링크(미등록 노드/엣지/순환)."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_opportunity(frm: str, to: str) -> bool:
    return _can(OPPORTUNITY_TRANSITIONS, frm, to)


def can_transition_recommendation(frm: str, to: str) -> bool:
    return _can(RECOMMENDATION_TRANSITIONS, frm, to)


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


def metadata_hash(metadata: dict) -> str:
    return _digest(dict(metadata or {}))


# ── 결정적 ID ──
def workflow_id(name: str, source_reference: str) -> str:
    return "SIW:" + hashlib.sha1(
        input_digest(name, source_reference).encode()).hexdigest()[:12]


def opportunity_id(category: str, description: str) -> str:
    return "SIO:" + hashlib.sha1(
        input_digest(category, description).encode()).hexdigest()[:12]


def opportunity_event_id(oid: str, frm: str, to: str) -> str:
    return "SOE:" + hashlib.sha1(input_digest(oid, frm, to).encode()).hexdigest()[:12]


def bottleneck_id(btype: str, impact: str) -> str:
    return "SIB:" + hashlib.sha1(input_digest(btype, impact).encode()).hexdigest()[:12]


def recommendation_id(target_process: str, suggestion: str) -> str:
    return "SIR:" + hashlib.sha1(
        input_digest(target_process, suggestion).encode()).hexdigest()[:12]


def recommendation_event_id(rid: str, frm: str, to: str) -> str:
    return "SRE:" + hashlib.sha1(input_digest(rid, frm, to).encode()).hexdigest()[:12]


def template_id(name: str, version: str) -> str:
    return "SIT:" + hashlib.sha1(input_digest(name, version).encode()).hexdigest()[:12]


def evidence_id(owner_ref: str, name: str) -> str:
    return "SIE:" + hashlib.sha1(input_digest(owner_ref, name).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "SIP:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "SIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def edge_id(from_ref: str, edge_type: str, to_ref: str) -> str:
    return "SIG:" + hashlib.sha1(
        input_digest(from_ref, edge_type, to_ref).encode()).hexdigest()[:12]


# ── Improvement analysis(결정적) ──
def improvement_score(metrics: dict) -> float:
    """가중 개선 근거 점수(0~1). **IMPROVEMENT SUGGESTION ≠ ACTION.**"""
    total = 0.0
    for key, wt in IMPROVEMENT_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


def improvement_confidence(metrics: dict) -> str:
    """개선 지표 → HIGH/MEDIUM/LOW. **자동 조치 없음 — AUTO_FIX/AUTO_APPLY/DEPLOY 아님.**"""
    s = improvement_score(metrics)
    if s >= 0.7:
        return HIGH
    if s >= 0.4:
        return MEDIUM
    return LOW


def detect_cycle(edges: list) -> list:
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}
    path: list = []

    def dfs(node) -> list:
        color[node] = GRAY
        path.append(node)
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return path[path.index(nxt):] + [nxt]
            if c == WHITE:
                r = dfs(nxt)
                if r:
                    return r
        path.pop()
        color[node] = BLACK
        return []

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE:
            r = dfs(node)
            if r:
                return r
    return []


def workflow_diff(steps_a: list, steps_b: list) -> dict:
    """두 워크플로 단계 집합의 서술적 차이(자동 선택 아님)."""
    sa, sb = set(steps_a or []), set(steps_b or [])
    return {"only_a": sorted(sa - sb), "only_b": sorted(sb - sa),
            "shared": sorted(sa & sb), "jaccard": round(len(sa & sb) / len(sa | sb), 8)
            if (sa | sb) else 0.0}


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class WorkflowPattern:
    workflow_id: str
    name: str
    steps: list
    source_reference: str
    execution_history: list
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OpportunityEvent:
    event_id: str
    opportunity_id: str
    category: str
    description: str
    severity: str
    evidence_refs: list
    confidence: float
    from_state: str
    to_state: str
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BottleneckRecord:
    bottleneck_id: str
    bottleneck_type: str
    frequency: int
    impact: str
    evidence: list
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecommendationEvent:
    event_id: str
    recommendation_id: str
    target_process: str
    suggestion: str
    expected_benefit: str
    supporting_evidence: list
    confidence: float
    from_state: str
    to_state: str
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TemplateEvolution:
    template_id: str
    name: str
    version: str
    changes: list
    reason: str
    evidence: list
    parent_version: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementEvidence:
    evidence_id: str
    owner_ref: str
    name: str
    metric: str
    value: float
    interpretation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementReport:
    report_id: str
    scope: str
    workflow_count: int
    bottleneck_count: int
    opportunity_count: int
    opportunity_severity_distribution: dict
    recommendation_count: int
    recommendation_state_distribution: dict
    template_count: int
    metrics: dict
    improvement_score: float
    improvement_confidence: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    from_ref: str
    to_ref: str
    edge_type: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementSummary:
    timestamp: str
    workflow_count: int
    opportunity_count: int
    opportunity_state_distribution: dict
    bottleneck_count: int
    recommendation_count: int
    recommendation_state_distribution: dict
    template_count: int
    evidence_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
