"""Research Meta Intelligence 자료형 (P10.12) — 연구 과정 자체를 연구하는 메타 분석 전용.

P10.2~P10.11 연구 계층 이력을 **READ ONLY** 로 소비해 연구 패턴·방법·결과 이력·실패 패턴·연구 품질·
메타 인사이트를 기록한다. **연구 이력 분석만 수행한다.** trading signal 생성·strategy 선택·model 승인·
capital 배분·deploy 없음. META SCORE ≠ TRADING SCORE · RESEARCH QUALITY ≠ PERFORMANCE GUARANTEE ·
INSIGHT ≠ DECISION. 불변·append-only 해시체인·결정적. 물리 원장은 mi_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Pattern 생명주기 ──
DISCOVERED = "DISCOVERED"
ANALYZED = "ANALYZED"
CONFIRMED = "CONFIRMED"
ARCHIVED = "ARCHIVED"

PATTERN_STATES = (DISCOVERED, ANALYZED, CONFIRMED, ARCHIVED)
PATTERN_TRANSITIONS = {
    "": {DISCOVERED},
    DISCOVERED: {ANALYZED},
    ANALYZED: {CONFIRMED},
    CONFIRMED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Outcome 생명주기 ──
RECORDED = "RECORDED"
REVIEWED = "REVIEWED"
CLASSIFIED = "CLASSIFIED"

OUTCOME_STATES = (RECORDED, REVIEWED, CLASSIFIED)
OUTCOME_TRANSITIONS = {
    "": {RECORDED},
    RECORDED: {REVIEWED},
    REVIEWED: {CLASSIFIED},
    CLASSIFIED: set(),
}

# ── Insight 생명주기 ──
GENERATED = "GENERATED"
# REVIEWED / ARCHIVED 공유

INSIGHT_STATES = (GENERATED, REVIEWED, ARCHIVED)
INSIGHT_TRANSITIONS = {
    "": {GENERATED},
    GENERATED: {REVIEWED},
    REVIEWED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Outcome 결과 유형 ──
SUCCESS = "SUCCESS"
FAILED = "FAILED"
WARNING = "WARNING"
INCONCLUSIVE = "INCONCLUSIVE"
RESULT_TYPES = (SUCCESS, FAILED, WARNING, INCONCLUSIVE)

# ── Meta insight 신뢰도 ──
HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
MEDIUM_CONFIDENCE = "MEDIUM_CONFIDENCE"
LOW_CONFIDENCE = "LOW_CONFIDENCE"

# ── 실패 카테고리(예시) ──
OVERFITTING = "overfitting"
INSUFFICIENT_DATA = "insufficient_data"
UNSTABLE_PARAMETERS = "unstable_parameters"
REGIME_DEPENDENCY = "regime_dependency"
EXCESSIVE_COST = "excessive_cost"
FAILURE_CATEGORIES = (OVERFITTING, INSUFFICIENT_DATA, UNSTABLE_PARAMETERS, REGIME_DEPENDENCY,
                      EXCESSIVE_COST)

# ── 연구 방법(예시) ──
WALK_FORWARD_VALIDATION = "walk_forward_validation"
MONTE_CARLO_TEST = "monte_carlo_test"
ABLATION_TEST = "ablation_test"
REGIME_TEST = "regime_test"
STRESS_TEST = "stress_test"
RESEARCH_METHODS = (WALK_FORWARD_VALIDATION, MONTE_CARLO_TEST, ABLATION_TEST, REGIME_TEST,
                    STRESS_TEST)

# ── 연구 패턴 카테고리(예시) ──
SHORT_LOOKBACK_OPTIMIZATION = "short_lookback_optimization"
EXCESSIVE_PARAMETER_SEARCH = "excessive_parameter_search"
UNSTABLE_VALIDATION_WINDOW = "unstable_validation_window"
HIGH_TURNOVER_DESIGN = "high_turnover_design"

# ── 연구 진화 그래프 노드 유형 ──
NODE_METHOD = "METHOD"
NODE_EXPERIMENT = "EXPERIMENT"
NODE_STRATEGY = "STRATEGY"
NODE_SIGNAL = "SIGNAL"
NODE_DATASET = "DATASET"
NODE_VALIDATION = "VALIDATION"
NODE_FAILURE = "FAILURE"
NODE_INSIGHT = "INSIGHT"
NODE_TYPES = (NODE_METHOD, NODE_EXPERIMENT, NODE_STRATEGY, NODE_SIGNAL, NODE_DATASET,
              NODE_VALIDATION, NODE_FAILURE, NODE_INSIGHT)

# ── 진화 그래프 엣지 유형 ──
USED_BY = "USED_BY"
LED_TO = "LED_TO"
FAILED_BECAUSE = "FAILED_BECAUSE"
SUPPORTED_BY = "SUPPORTED_BY"
IMPROVED_BY = "IMPROVED_BY"
EDGE_TYPES = (USED_BY, LED_TO, FAILED_BECAUSE, SUPPORTED_BY, IMPROVED_BY)

# ── Research Quality Score 가중치(합=1.0) ──
QUALITY_WEIGHTS = {
    "reproducibility": 0.20,
    "validation_depth": 0.20,
    "data_quality": 0.15,
    "robustness": 0.15,
    "lineage_completeness": 0.15,
    "evidence_strength": 0.15,
}

# ── Meta evaluation 가중치(합=1.0 for positive; failure_recurrence 감점) ──
META_POSITIVE_WEIGHTS = {
    "research_reliability": 0.30,
    "validation_consistency": 0.25,
    "method_effectiveness": 0.25,
    "evidence_completeness": 0.20,
}

# ── Artifact 유형(계보) ──
ART_SOURCE = "SOURCE"
ART_OUTCOME = "OUTCOME"
ART_PATTERN = "PATTERN"
ART_FAILURE = "FAILURE"
ART_QUALITY = "QUALITY"
ART_INSIGHT = "INSIGHT"
ART_REPORT = "REPORT"
ART_EDGE = "EVOLUTION_EDGE"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutablePatternError(Exception):
    """불변 연구 패턴 위반."""


class ImmutableMethodError(Exception):
    """불변 연구 방법 위반."""


class ImmutableFailureError(Exception):
    """불변 실패 패턴 위반."""


class UnknownPattern(Exception):
    """미등록 패턴 참조."""


class UnknownOutcome(Exception):
    """미등록 결과 참조."""


class UnknownInsight(Exception):
    """미등록 인사이트 참조."""


class InvalidEvolutionLink(Exception):
    """유효하지 않은 진화 그래프 링크(미등록 노드/순환)."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_pattern(frm: str, to: str) -> bool:
    return _can(PATTERN_TRANSITIONS, frm, to)


def can_transition_outcome(frm: str, to: str) -> bool:
    return _can(OUTCOME_TRANSITIONS, frm, to)


def can_transition_insight(frm: str, to: str) -> bool:
    return _can(INSIGHT_TRANSITIONS, frm, to)


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
def pattern_id(category: str, description: str) -> str:
    return "MIP:" + hashlib.sha1(input_digest(category, description).encode()).hexdigest()[:12]


def pattern_event_id(pid: str, frm: str, to: str) -> str:
    return "MPE:" + hashlib.sha1(input_digest(pid, frm, to).encode()).hexdigest()[:12]


def method_id(name: str, version: str) -> str:
    return "MIM:" + hashlib.sha1(input_digest(name, version).encode()).hexdigest()[:12]


def outcome_id(source_layer: str, research_object: str) -> str:
    return "MIO:" + hashlib.sha1(
        input_digest(source_layer, research_object).encode()).hexdigest()[:12]


def outcome_event_id(oid: str, frm: str, to: str) -> str:
    return "MOE:" + hashlib.sha1(input_digest(oid, frm, to).encode()).hexdigest()[:12]


def failure_id(category: str) -> str:
    return "MIF:" + hashlib.sha1(input_digest(category).encode()).hexdigest()[:12]


def quality_score_id(research_object: str) -> str:
    return "MIQ:" + hashlib.sha1(input_digest(research_object).encode()).hexdigest()[:12]


def insight_id(topic: str, statement: str) -> str:
    return "MII:" + hashlib.sha1(input_digest(topic, statement).encode()).hexdigest()[:12]


def insight_event_id(iid: str, frm: str, to: str) -> str:
    return "MIE:" + hashlib.sha1(input_digest(iid, frm, to).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "MIR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "MIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def edge_id(from_ref: str, edge_type: str, to_ref: str) -> str:
    return "MIG:" + hashlib.sha1(
        input_digest(from_ref, edge_type, to_ref).encode()).hexdigest()[:12]


# ── Research Quality (0~100, 결정적) ──
def compute_quality(components: dict) -> float:
    """가중 연구 품질 점수(0~100). **quality_score ≠ strategy ranking · ≠ performance.**"""
    total = 0.0
    for key, wt in QUALITY_WEIGHTS.items():
        total += float(components.get(key, 0.0)) * float(wt)
    return round(total * 100.0, 6)


def quality_grade(score: float) -> str:
    s = float(score)
    if s >= 85:
        return "A"
    if s >= 70:
        return "B"
    if s >= 50:
        return "C"
    return "D"


# ── Meta evaluation (결정적) ──
def meta_score(metrics: dict) -> float:
    """긍정 지표 가중 평균 - 실패 재발 감점 → 0~1. INSIGHT ≠ DECISION."""
    pos = 0.0
    for key, wt in META_POSITIVE_WEIGHTS.items():
        pos += float(metrics.get(key, 0.0)) * float(wt)
    recurrence = float(metrics.get("failure_recurrence", 0.0))
    return round(max(0.0, min(1.0, pos - 0.3 * recurrence)), 8)


def meta_insight(metrics: dict) -> str:
    """메타 지표 → HIGH/MEDIUM/LOW_CONFIDENCE. **자동 조치 없음.**"""
    s = meta_score(metrics)
    if s >= 0.7:
        return HIGH_CONFIDENCE
    if s >= 0.4:
        return MEDIUM_CONFIDENCE
    return LOW_CONFIDENCE


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
class PatternEvent:
    event_id: str
    pattern_id: str
    category: str
    description: str
    frequency: int
    source_references: list
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
class ResearchMethod:
    method_id: str
    name: str
    version: str
    category: str
    usage_count: int
    success_rate: float
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OutcomeEvent:
    event_id: str
    outcome_id: str
    source_layer: str
    research_object: str
    result_type: str                # SUCCESS | FAILED | WARNING | INCONCLUSIVE
    metrics: dict
    validation_reference: str
    method_reference: str
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
class FailurePattern:
    failure_id: str
    category: str
    occurrences: int
    examples: list
    confidence: float
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchQualityScore:
    score_id: str
    research_object: str
    components: dict
    overall_score: float            # 0~100 (품질 — 성능/랭킹 아님)
    grade: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InsightEvent:
    event_id: str
    insight_id: str
    topic: str
    statement: str
    metrics: dict
    meta_confidence: str            # HIGH | MEDIUM | LOW _CONFIDENCE
    evidence_references: list
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
class MetaReport:
    report_id: str
    scope: str
    outcome_count: int
    result_distribution: dict
    pattern_count: int
    failure_count: int
    method_count: int
    mean_quality: float
    insight_count: int
    meta_confidence_distribution: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetaArtifact:
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
class MetaSummary:
    timestamp: str
    pattern_count: int
    pattern_state_distribution: dict
    method_count: int
    outcome_count: int
    outcome_state_distribution: dict
    result_distribution: dict
    failure_count: int
    quality_score_count: int
    mean_quality: float
    insight_count: int
    insight_confidence_distribution: dict
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
