"""Autonomous Research Evaluation 자료형 (P12.5) — 자율 연구 사이클 평가. **평가·기록 전용.**

연구 품질·재현성·효율·강건성·지식 기여를 측정한다. **점수는 승인이 아니고 배포 권한이 아니다.** SCORE ≠ APPROVAL ·
SCORE ≠ DEPLOYMENT PERMISSION · EVALUATION ≠ SELECTION. 불변·append-only·이벤트 소싱·SHA256 해시체인·결정적.
물리 원장은 are_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 평가 생애주기(5) ──
E_CREATED = "CREATED"
E_EVALUATING = "EVALUATING"
E_SCORED = "SCORED"
E_REVIEWED = "REVIEWED"
E_ARCHIVED = "ARCHIVED"
EVAL_STATES = (E_CREATED, E_EVALUATING, E_SCORED, E_REVIEWED, E_ARCHIVED)

ALLOWED_TRANSITIONS = {
    E_CREATED: {E_EVALUATING},
    E_EVALUATING: {E_SCORED},
    E_SCORED: {E_REVIEWED},
    E_REVIEWED: {E_ARCHIVED, E_EVALUATING},
    E_ARCHIVED: set(),
}

# ── 평가 차원(6) ──
DIM_RESEARCH_QUALITY = "RESEARCH_QUALITY"
DIM_REPRODUCIBILITY = "REPRODUCIBILITY"
DIM_EVIDENCE_STRENGTH = "EVIDENCE_STRENGTH"
DIM_EFFICIENCY = "EFFICIENCY"
DIM_ROBUSTNESS = "ROBUSTNESS"
DIM_KNOWLEDGE_CONTRIBUTION = "KNOWLEDGE_CONTRIBUTION"
EVAL_DIMENSIONS = (DIM_RESEARCH_QUALITY, DIM_REPRODUCIBILITY, DIM_EVIDENCE_STRENGTH, DIM_EFFICIENCY,
                   DIM_ROBUSTNESS, DIM_KNOWLEDGE_CONTRIBUTION)

# ── 아티팩트(계보) 유형 ──
ART_EVALUATION = "EVALUATION"
ART_REPORT = "REPORT"

# ── 금지(승인·배포·선택) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "APPROVE_LIVE", "DEPLOY", "SELECT_STRATEGY", "ALLOCATE_CAPITAL", "APPROVE", "PROMOTE",
    "PROMOTE_LIVE", "EXECUTE", "TRADE", "ALLOCATE",
})


class ImmutableCriterionError(Exception):
    """불변 평가 기준 위반."""


class ImmutableScoreError(Exception):
    """불변 점수(중복 차원) 위반."""


class ImmutableEvaluationError(Exception):
    """불변 평가(중복) 위반."""


class ImmutableBenchmarkError(Exception):
    """불변 벤치마크 위반."""


class IllegalEvalTransition(Exception):
    """유효하지 않은 평가 상태 전이 — 거부."""


class InvalidDimension(Exception):
    """미등록 평가 차원."""


class UnknownEvaluationError(Exception):
    """미등록 평가 참조."""


class UnknownCriterionError(Exception):
    """미등록 기준 참조."""


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


# ── 결정적 ID (EV* 스킴) ──
def evaluation_id(research_layer: str, research_ref: str) -> str:
    return "EVG:" + hashlib.sha1(
        input_digest(research_layer, research_ref).encode()).hexdigest()[:12]


def evaluation_event_id(evaluation: str, to_state: str, seq: int) -> str:
    return "EVR:" + hashlib.sha1(input_digest(evaluation, to_state, seq).encode()).hexdigest()[:12]


def criterion_id(name: str) -> str:
    return "EVM:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def score_id(evaluation: str, dimension: str) -> str:
    return "EVS:" + hashlib.sha1(input_digest(evaluation, dimension).encode()).hexdigest()[:12]


def benchmark_id(eval_a: str, eval_b: str, metric: str) -> str:
    return "EVB:" + hashlib.sha1(input_digest(eval_a, eval_b, metric).encode()).hexdigest()[:12]


def report_id(scope: str, scope_id: str, generated_at: str) -> str:
    return "EVO:" + hashlib.sha1(
        input_digest(scope, scope_id, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "EVL:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def weighted_score(scores: dict, weights: dict = None) -> float:
    """차원별 점수의 가중 평균(결정적). scores/weights: {dimension: value}. 빈 경우 0.0."""
    weights = weights or {}
    if not scores:
        return 0.0
    total_w = 0.0
    acc = 0.0
    for dim in sorted(scores):
        w = float(weights.get(dim, 1.0))
        acc += float(scores[dim]) * w
        total_w += w
    return round(acc / total_w, 6) if total_w else 0.0


def compare_direction(value_a: float, value_b: float) -> tuple:
    """벤치마크 비교(높을수록 우수, 결정적). 반환 (winner, delta). winner ∈ {A,B,TIE}."""
    delta = round(float(value_b) - float(value_a), 8)
    if delta == 0:
        return "TIE", 0.0
    return ("B" if delta > 0 else "A"), delta


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


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class EvaluationEventRecord:
    evaluation_event_id: str
    evaluation_id: str
    research_layer: str
    research_ref: str
    overall_score: float
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
class CriterionRecord:
    criterion_id: str
    name: str
    dimension: str
    weight: float
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScoreRecord:
    score_id: str
    evaluation_id: str
    dimension: str
    score: float
    evidence_ref: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkRecord:
    benchmark_id: str
    eval_a: str
    eval_b: str
    metric: str
    value_a: float
    value_b: float
    winner: str
    delta: float
    compared_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QualityReportRecord:
    report_id: str
    scope: str
    scope_id: str
    evaluation_count: int
    scored_count: int
    reviewed_count: int
    dimension_averages: dict
    is_approval: bool
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
class EvaluationSummary:
    timestamp: str
    evaluation_event_count: int
    criterion_count: int
    score_count: int
    benchmark_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
