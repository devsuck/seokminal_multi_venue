"""Research Planning Intelligence 자료형 (P10.15) — 역사적 근거로 미래 연구 방향을 조직하는 계획 전용.

P10.5·P10.7·P10.8·P10.11·P10.12·P10.13·P10.14 를 **READ ONLY** 로 소비해 연구 기회·로드맵·실험
청사진·의존 분석·우선순위·계획 리포트를 기록한다. **실험 자동 시작·strategy 선택·resource 배분·agent
실행·model 배포 없음.** PLAN ≠ EXECUTION · PRIORITY ≠ APPROVAL · OPPORTUNITY ≠ GUARANTEED VALUE.
불변·append-only 해시체인·결정적. 물리 원장은 rp_ 접두사.
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
PLANNED = "PLANNED"
ARCHIVED = "ARCHIVED"

OPPORTUNITY_STATES = (IDENTIFIED, ANALYZED, PLANNED, ARCHIVED)
OPPORTUNITY_TRANSITIONS = {
    "": {IDENTIFIED},
    IDENTIFIED: {ANALYZED},
    ANALYZED: {PLANNED},
    PLANNED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 복잡도 라벨(서술) ──
COMPLEXITY_LOW = "LOW"
COMPLEXITY_MEDIUM = "MEDIUM"
COMPLEXITY_HIGH = "HIGH"
COMPLEXITY_LEVELS = (COMPLEXITY_LOW, COMPLEXITY_MEDIUM, COMPLEXITY_HIGH)
_COMPLEXITY_VALUE = {COMPLEXITY_LOW: 0.2, COMPLEXITY_MEDIUM: 0.5, COMPLEXITY_HIGH: 0.85}

# ── 의존 그래프 노드 유형 ──
NODE_DATASET = "DATASET"
NODE_FEATURE = "FEATURE"
NODE_SIGNAL = "SIGNAL"
NODE_STRATEGY = "STRATEGY"
NODE_MODEL = "MODEL"
NODE_EXPERIMENT = "EXPERIMENT"
NODE_VALIDATION = "VALIDATION"
NODE_TYPES = (NODE_DATASET, NODE_FEATURE, NODE_SIGNAL, NODE_STRATEGY, NODE_MODEL,
              NODE_EXPERIMENT, NODE_VALIDATION)

# ── 의존 그래프 엣지 유형 ──
REQUIRES = "REQUIRES"
BUILDS_ON = "BUILDS_ON"
DEPENDS_ON = "DEPENDS_ON"
EDGE_TYPES = (REQUIRES, BUILDS_ON, DEPENDS_ON)

# ── Planning confidence 라벨 ──
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# ── Planning analysis 가중치(positive 합=1.0; complexity 감점) ──
PLANNING_WEIGHTS = {
    "expected_learning_value": 0.30,
    "evidence_availability": 0.25,
    "validation_feasibility": 0.20,
    "historical_success": 0.25,
}

# ── Artifact 유형(계보) ──
ART_SOURCE = "SOURCE"
ART_OPPORTUNITY = "OPPORTUNITY"
ART_HYPOTHESIS = "HYPOTHESIS"
ART_BLUEPRINT = "BLUEPRINT"
ART_PLAN = "PLAN"
ART_DEPENDENCY = "DEPENDENCY"
ART_PRIORITY = "PRIORITY"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 기회 생명주기 전이."""


class ImmutableOpportunityError(Exception):
    """불변 연구 기회 위반."""


class ImmutableBlueprintError(Exception):
    """불변 청사진 위반."""


class ImmutablePlanError(Exception):
    """불변 계획 위반."""


class ImmutableHypothesisError(Exception):
    """불변 계획 가설 위반."""


class UnknownOpportunity(Exception):
    """미등록 기회 참조."""


class UnknownPlan(Exception):
    """미등록 계획 참조."""


class InvalidDependency(Exception):
    """유효하지 않은 의존(미등록 노드 유형/엣지/순환)."""


def can_transition_opportunity(frm: str, to: str) -> bool:
    return to in OPPORTUNITY_TRANSITIONS.get(frm, set())


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
def opportunity_id(description: str) -> str:
    return "RPO:" + hashlib.sha1(input_digest(description).encode()).hexdigest()[:12]


def opportunity_event_id(oid: str, frm: str, to: str) -> str:
    return "ROE:" + hashlib.sha1(input_digest(oid, frm, to).encode()).hexdigest()[:12]


def plan_id(name: str) -> str:
    return "RPP:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def blueprint_id(objective: str, method: str) -> str:
    return "RPB:" + hashlib.sha1(input_digest(objective, method).encode()).hexdigest()[:12]


def hypothesis_id(statement: str) -> str:
    return "RPH:" + hashlib.sha1(input_digest(statement).encode()).hexdigest()[:12]


def dependency_id(from_node: str, edge_type: str, to_node: str) -> str:
    return "RPD:" + hashlib.sha1(
        input_digest(from_node, edge_type, to_node).encode()).hexdigest()[:12]


def priority_id(plan_ref: str) -> str:
    return "RPR:" + hashlib.sha1(input_digest(plan_ref).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "RPT:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RPA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── Planning analysis(결정적) ──
def complexity_value(level: str) -> float:
    return _COMPLEXITY_VALUE.get(level, 0.5)


def planning_score(metrics: dict) -> float:
    """positive 가중 - complexity 감점 → 0~1. **PRIORITY ≠ APPROVAL · OPPORTUNITY ≠ VALUE.**"""
    pos = 0.0
    for key, wt in PLANNING_WEIGHTS.items():
        pos += float(metrics.get(key, 0.0)) * float(wt)
    complexity = float(metrics.get("complexity", 0.0))
    return round(max(0.0, min(1.0, pos - 0.3 * complexity)), 8)


def planning_confidence(metrics: dict) -> str:
    """계획 지표 → HIGH/MEDIUM/LOW. **자동 조치 없음 — PLAN ≠ EXECUTION.**"""
    s = planning_score(metrics)
    if s >= 0.7:
        return HIGH
    if s >= 0.4:
        return MEDIUM
    return LOW


def priority_score(metrics: dict) -> float:
    """우선순위 점수(정보용) = planning_score. 승인/실행 아님."""
    return planning_score(metrics)


def priority_rank(score: float) -> str:
    s = float(score)
    if s >= 0.7:
        return "P1"
    if s >= 0.4:
        return "P2"
    return "P3"


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


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class OpportunityEvent:
    event_id: str
    opportunity_id: str
    description: str
    source_evidence: list
    expected_learning: str
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
class PlanningHypothesis:
    hypothesis_id: str
    statement: str
    rationale: str
    evidence_refs: list
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchBlueprint:
    """가능한 실험 구조 정의. **실행 없음.**"""
    blueprint_id: str
    objective: str
    inputs: list
    method: str
    validation_requirements: list
    dependencies: list
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchPlan:
    plan_id: str
    name: str
    opportunities: list
    dependencies: list
    priority_score: float           # 정보용 — 승인 아님
    estimated_complexity: str
    expected_value: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyEdge:
    dependency_id: str
    from_node: str
    from_type: str
    edge_type: str                  # REQUIRES | BUILDS_ON | DEPENDS_ON
    to_node: str
    to_type: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PriorityAnalysis:
    priority_id: str
    plan_ref: str
    components: dict
    priority_score: float           # 정보용
    rank: str                       # P1 | P2 | P3 (정보용 — 승인 아님)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlanningReport:
    report_id: str
    scope: str
    opportunity_count: int
    opportunity_state_distribution: dict
    plan_count: int
    blueprint_count: int
    hypothesis_count: int
    dependency_count: int
    priority_count: int
    metrics: dict
    planning_score: float
    planning_confidence: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlanningArtifact:
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
class PlanningSummary:
    timestamp: str
    opportunity_count: int
    opportunity_state_distribution: dict
    plan_count: int
    blueprint_count: int
    hypothesis_count: int
    dependency_count: int
    edge_type_distribution: dict
    priority_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
