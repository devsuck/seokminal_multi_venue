"""Research Self-Improvement Loop 자료형 (P11.10) — 연구 개선 계층. **분석·기록 전용.**

이전 연구 활동을 분석해 개선 기회를 기록한다(연구 프로세스 평가·워크플로 개선 발굴·반복 실수 탐지·효율 분석·
지식 재사용 분석·방법론 개선 추적). **이전 연구·전략·모델을 수정하지 않고 배포 승인·자동 실험 실행·설정 변경을
하지 않는다.** ACCEPTED 는 연구 프로세스 수용일 뿐 — 전략/모델/배포 승인·거래 활성화가 아니다.
IMPROVEMENT ≠ EXECUTION · ACCEPTED ≠ DEPLOYMENT · PROPOSAL ≠ APPROVAL. 불변·append-only·이벤트 소싱·SHA256 해시체인.
물리 원장은 rimp_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 개선 제안 생애주기(6) ──
I_OBSERVED = "OBSERVED"
I_ANALYZING = "ANALYZING"
I_PROPOSED = "PROPOSED"
I_REVIEWING = "REVIEWING"
I_ACCEPTED = "ACCEPTED"
I_ARCHIVED = "ARCHIVED"
IMPROVEMENT_STATES = (I_OBSERVED, I_ANALYZING, I_PROPOSED, I_REVIEWING, I_ACCEPTED, I_ARCHIVED)

ALLOWED_TRANSITIONS = {
    I_OBSERVED: {I_ANALYZING},
    I_ANALYZING: {I_PROPOSED},
    I_PROPOSED: {I_REVIEWING},
    I_REVIEWING: {I_ACCEPTED, I_ANALYZING},
    I_ACCEPTED: {I_ARCHIVED},
    I_ARCHIVED: set(),
}

# ── 개선 카테고리(7) ──
CAT_RESEARCH_QUALITY = "RESEARCH_QUALITY"
CAT_DATA_QUALITY = "DATA_QUALITY"
CAT_EXPERIMENT_DESIGN = "EXPERIMENT_DESIGN"
CAT_VALIDATION_PROCESS = "VALIDATION_PROCESS"
CAT_AGENT_COLLABORATION = "AGENT_COLLABORATION"
CAT_KNOWLEDGE_REUSE = "KNOWLEDGE_REUSE"
CAT_WORKFLOW_EFFICIENCY = "WORKFLOW_EFFICIENCY"
CATEGORIES = (CAT_RESEARCH_QUALITY, CAT_DATA_QUALITY, CAT_EXPERIMENT_DESIGN, CAT_VALIDATION_PROCESS,
              CAT_AGENT_COLLABORATION, CAT_KNOWLEDGE_REUSE, CAT_WORKFLOW_EFFICIENCY)

# ── 리뷰 결정 ──
DEC_ACCEPT = "ACCEPT"
DEC_REWORK = "REWORK"
DEC_NOTE = "NOTE"
DECISIONS = (DEC_ACCEPT, DEC_REWORK, DEC_NOTE)

# ── 반복 비교 방향 ──
DIR_IMPROVED = "IMPROVED"
DIR_REGRESSED = "REGRESSED"
DIR_UNCHANGED = "UNCHANGED"

# ── 아티팩트(계보) 유형 ──
ART_CYCLE = "CYCLE"
ART_IMPROVEMENT = "IMPROVEMENT"
ART_LEARNING = "LEARNING"
ART_REPORT = "REPORT"

# ── 금지(실행·승인·수정) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "APPROVE_STRATEGY", "APPROVE_MODEL", "PROMOTE_LIVE",
    "MODIFY_PERMISSION", "MODIFY_CONFIG", "APPROVE", "ACTIVATE", "MODIFY_STRATEGY", "MODIFY_MODEL",
})


class ImmutableRegistryError(Exception):
    """불변 레지스트리 위반."""


class ImmutableCycleError(Exception):
    """불변 연구 사이클 위반."""


class ImmutableObservationError(Exception):
    """불변 관측 위반."""


class ImmutableFailureError(Exception):
    """불변 실패 패턴 위반."""


class ImmutableImprovementError(Exception):
    """불변 개선(중복 개선 기록) 위반."""


class ImmutableLearningError(Exception):
    """불변 학습 기록 위반."""


class ImmutableReviewError(Exception):
    """불변 리뷰 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class InvalidCategory(Exception):
    """미등록 개선 카테고리."""


class InvalidDecision(Exception):
    """미등록 리뷰 결정."""


class IllegalImprovementTransition(Exception):
    """허용되지 않은 개선 상태 전이."""


class CircularLearningError(Exception):
    """순환 학습 의존성 — 거부."""


class DanglingReferenceError(Exception):
    """dangling 참조 — 거부."""


class MissingSourceError(Exception):
    """소스 참조 누락 — 거부."""


class UnknownRegistryError(Exception):
    """미등록 레지스트리 참조."""


class UnknownCycleError(Exception):
    """미등록 사이클 참조."""


class UnknownImprovementError(Exception):
    """미등록 개선 참조."""


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


# ── 결정적 ID ──
def registry_id(name: str) -> str:
    return "RIG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def cycle_id(registry: str, name: str, iteration: int) -> str:
    return "RIC:" + hashlib.sha1(
        input_digest(registry, name, iteration).encode()).hexdigest()[:12]


def observation_id(cycle: str, subject: str, metric: str) -> str:
    return "RIO:" + hashlib.sha1(input_digest(cycle, subject, metric).encode()).hexdigest()[:12]


def metric_id(cycle: str, metric: str) -> str:
    return "RIM:" + hashlib.sha1(input_digest(cycle, metric).encode()).hexdigest()[:12]


def failure_id(cycle: str, pattern_type: str, subject: str) -> str:
    return "RIF:" + hashlib.sha1(
        input_digest(cycle, pattern_type, subject).encode()).hexdigest()[:12]


def improvement_id(cycle: str, category: str, title: str) -> str:
    return "RIP:" + hashlib.sha1(input_digest(cycle, category, title).encode()).hexdigest()[:12]


def improvement_event_id(improvement: str, to_state: str, seq: int) -> str:
    return "RIE:" + hashlib.sha1(
        input_digest(improvement, to_state, seq).encode()).hexdigest()[:12]


def learning_id(cycle: str, lesson: str) -> str:
    return "RIL:" + hashlib.sha1(input_digest(cycle, lesson).encode()).hexdigest()[:12]


def iteration_id(cycle_a: str, cycle_b: str, metric: str) -> str:
    return "RIT:" + hashlib.sha1(
        input_digest(cycle_a, cycle_b, metric).encode()).hexdigest()[:12]


def review_id(improvement: str, reviewer: str, seq: int) -> str:
    return "RIV:" + hashlib.sha1(
        input_digest(improvement, reviewer, seq).encode()).hexdigest()[:12]


def report_id(cycle: str, scope: str, generated_at: str) -> str:
    return "RIR:" + hashlib.sha1(
        input_digest(cycle, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def compare_direction(value_a: float, value_b: float, higher_is_better: bool = True) -> tuple:
    """반복 비교 방향·델타(결정적). 반환 (direction, delta)."""
    delta = round(float(value_b) - float(value_a), 8)
    if delta == 0:
        return DIR_UNCHANGED, 0.0
    improved = (delta > 0) if higher_is_better else (delta < 0)
    return (DIR_IMPROVED if improved else DIR_REGRESSED), delta


def detect_cycle(edges: list) -> list:
    """방향 그래프 순환 탐지(DFS, 결정적). 첫 순환 경로 또는 []."""
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


def ancestors(edges: list, node: str) -> list:
    """node 의 모든 조상(전이적, 결정적)."""
    adj: dict = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
    seen: set = set()
    stack = [node]
    while stack:
        x = stack.pop()
        for nxt in sorted(adj.get(x, ())):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return sorted(seen)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class RegistryRecord:
    registry_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CycleRecord:
    cycle_id: str
    registry_id: str
    name: str
    scope: str
    iteration: int
    started_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservationRecord:
    observation_id: str
    cycle_id: str
    subject: str
    metric_name: str
    value: float
    unit: str
    source_layer: str
    source_ref: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetricRecord:
    metric_id: str
    cycle_id: str
    metric_name: str
    value: float
    category: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureRecord:
    failure_id: str
    cycle_id: str
    pattern_type: str
    subject: str
    description: str
    occurrences: int
    source_layer: str
    source_ref: str
    related_refs: list
    detected_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementEventRecord:
    improvement_event_id: str
    improvement_id: str
    cycle_id: str
    category: str
    title: str
    description: str
    proposed_change: str
    from_state: str
    to_state: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearningRecord:
    learning_id: str
    cycle_id: str
    lesson: str
    category: str
    source_layer: str
    source_ref: str
    parent_learning: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IterationRecord:
    iteration_id: str
    cycle_a: str
    cycle_b: str
    metric_name: str
    value_a: float
    value_b: float
    delta: float
    direction: str
    compared_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    improvement_id: str
    reviewer: str
    decision: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementReportRecord:
    report_id: str
    cycle_id: str
    scope: str
    observation_count: int
    failure_count: int
    proposal_count: int
    accepted_count: int
    learning_count: int
    category_distribution: dict
    process_acceptance_only: bool
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
    cycle_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementSummary:
    timestamp: str
    registry_count: int
    cycle_count: int
    observation_count: int
    metric_count: int
    failure_count: int
    improvement_event_count: int
    learning_count: int
    iteration_count: int
    review_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
