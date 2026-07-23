"""Research Decision Intelligence 자료형 (P10.7) — 연구 결과 비교·분석 판단 지원 전용.

여러 연구 결과(P10.2~P10.6)를 **READ ONLY** 로 소비해 사람이 검토 가능한 형태로 비교·분석한다.
**판단 지원만 수행한다.** 자동 전략 선택·trading permission·deployment·capital allocation·portfolio
mutation·model promotion·execution·broker·risk threshold·permission 변경 없음. Decision output 은
기록 데이터이며 실제 운영 상태를 바꾸지 않는다. score ≠ approval · score ≠ deployment permission ·
VALIDATED ≠ SELECTED · RECOMMENDED ≠ DEPLOYABLE. 불변·append-only 해시체인·결정적. 물리 원장 di_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Candidate 생명주기 ──
REGISTERED = "REGISTERED"
UNDER_REVIEW = "UNDER_REVIEW"
SCORED = "SCORED"
COMPARED = "COMPARED"
REPORTED = "REPORTED"
ARCHIVED = "ARCHIVED"

CANDIDATE_STATES = (REGISTERED, UNDER_REVIEW, SCORED, COMPARED, REPORTED, ARCHIVED)
CANDIDATE_TRANSITIONS = {
    "": {REGISTERED},
    REGISTERED: {UNDER_REVIEW},
    UNDER_REVIEW: {SCORED},
    SCORED: {COMPARED, REPORTED},
    COMPARED: {REPORTED},
    REPORTED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Decision Session 생명주기 ──
CREATED = "CREATED"
EVALUATING = "EVALUATING"
COMPLETED = "COMPLETED"
# ARCHIVED 공유

SESSION_STATES = (CREATED, EVALUATING, COMPLETED, ARCHIVED)
SESSION_TRANSITIONS = {
    "": {CREATED},
    CREATED: {EVALUATING},
    EVALUATING: {COMPLETED},
    COMPLETED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 연구 유형(라벨 — 서술적) ──
RESEARCH_TYPES = ("STRATEGY", "SIGNAL", "PORTFOLIO", "GRAPH", "AGENT_RESEARCH")

# ── Scorecard 평가 항목 ──
PERFORMANCE = "performance"
ROBUSTNESS = "robustness"
RISK = "risk"
COMPLEXITY = "complexity"
DATA_QUALITY = "data_quality"
REPRODUCIBILITY = "reproducibility"
CONFIDENCE = "confidence"
SCORE_DIMENSIONS = (PERFORMANCE, ROBUSTNESS, RISK, COMPLEXITY, DATA_QUALITY,
                    REPRODUCIBILITY, CONFIDENCE)

# 기본 MCDA 가중치(합=1.0). complexity/risk 는 낮을수록 좋으나 점수는 정규화된 '좋음' 값으로 입력.
DEFAULT_WEIGHTS = {
    PERFORMANCE: 0.30,
    ROBUSTNESS: 0.25,
    RISK: 0.20,
    COMPLEXITY: 0.10,
    DATA_QUALITY: 0.10,
    CONFIDENCE: 0.05,
}

# ── Artifact 유형(계보) ──
ART_SOURCE = "SOURCE"
ART_CANDIDATE = "CANDIDATE"
ART_EVALUATION = "EVALUATION"
ART_SCORECARD = "SCORECARD"
ART_TRADEOFF = "TRADEOFF"
ART_REPORT = "REPORT"

_EPS = 1e-9


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableCandidateError(Exception):
    """불변 후보 위반(동일 candidate_id 내용 상이)."""


class ImmutableFrameworkError(Exception):
    """불변 평가 프레임워크 위반(동일 framework_id+version 내용 상이)."""


class UnknownCandidate(Exception):
    """미등록 후보 참조."""


class UnknownFramework(Exception):
    """미등록 프레임워크 참조."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_candidate(frm: str, to: str) -> bool:
    return _can(CANDIDATE_TRANSITIONS, frm, to)


def can_transition_session(frm: str, to: str) -> bool:
    return _can(SESSION_TRANSITIONS, frm, to)


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
def candidate_id(source_layer: str, source_reference: str) -> str:
    return "DIC:" + hashlib.sha1(
        input_digest(source_layer, source_reference).encode()).hexdigest()[:12]


def candidate_event_id(cid: str, frm: str, to: str) -> str:
    return "DCE:" + hashlib.sha1(input_digest(cid, frm, to).encode()).hexdigest()[:12]


def session_id(objective: str, evaluator: str, candidates: list) -> str:
    return "DSS:" + hashlib.sha1(
        input_digest(objective, evaluator, sorted(candidates or [])).encode()).hexdigest()[:12]


def session_event_id(sid: str, frm: str, to: str) -> str:
    return "DSE:" + hashlib.sha1(input_digest(sid, frm, to).encode()).hexdigest()[:12]


def framework_id(name: str, version: str) -> str:
    return "DFW:" + hashlib.sha1(input_digest(name, version).encode()).hexdigest()[:12]


def scorecard_id(session_id_: str, candidate_id_: str, framework_id_: str) -> str:
    return "DSC:" + hashlib.sha1(
        input_digest(session_id_, candidate_id_, framework_id_).encode()).hexdigest()[:12]


def tradeoff_id(session_id_: str, candidate_a: str, candidate_b: str) -> str:
    a, b = sorted((candidate_a, candidate_b))
    return "DTO:" + hashlib.sha1(input_digest(session_id_, a, b).encode()).hexdigest()[:12]


def report_id(session_id_: str) -> str:
    return "DRP:" + hashlib.sha1(input_digest(session_id_).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "DIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── MCDA 계산(결정적) ──
def normalize_weights(weights: dict) -> dict:
    total = sum(abs(float(w)) for w in (weights or {}).values())
    if total < _EPS:
        return dict(weights or {})
    return {k: round(float(v) / total, 8) for k, v in weights.items()}


def overall_score(scores: dict, weights: dict) -> float:
    """가중 종합 점수(MCDA). score ≠ approval · score ≠ deployment permission — 판단 지원 값일 뿐."""
    w = normalize_weights(weights)
    total = 0.0
    for dim, wt in w.items():
        total += float(scores.get(dim, 0.0)) * float(wt)
    return round(total, 8)


def tradeoff_symbol(score: float) -> str:
    """0~1 점수를 서술적 기호로(+++/++/+/-). 자동 추천 아님 — 사람 검토용 요약."""
    s = float(score)
    if s >= 0.75:
        return "+++"
    if s >= 0.5:
        return "++"
    if s >= 0.25:
        return "+"
    return "-"


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
class CandidateEvent:
    """연구 후보 등록·상태 전이 이벤트(이벤트 소싱). candidate 정체성 불변."""
    event_id: str
    candidate_id: str
    source_layer: str
    source_reference: str
    research_type: str
    metadata_hash: str
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
class DecisionSessionEvent:
    event_id: str
    session_id: str
    objective: str
    evaluator: str
    candidates: list
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
class EvaluationFramework:
    framework_id: str
    name: str
    version: str
    criteria: list
    weights: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Scorecard:
    scorecard_id: str
    session_id: str
    candidate_id: str
    framework_id: str
    scores: dict                    # {dim: score 0~1}
    evidence: dict                  # {dim: evidence_reference}
    explanations: dict              # {dim: explanation}
    overall_score: float            # 가중 종합(판단 지원 값 — 승인/배포 아님)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TradeoffAnalysis:
    tradeoff_id: str
    session_id: str
    candidate_a: str
    candidate_b: str
    dimensions: dict                # {dim: {a: sym, b: sym, delta: float}}
    overall_a: float
    overall_b: float
    note: str                       # 자동 추천 없음 — 서술적 요약만
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DecisionReport:
    report_id: str
    session_id: str
    objective: str
    evaluator: str
    candidate_count: int
    ranking: list                   # [{candidate_id, overall_score}] 정렬(선택 아님 — 참고용)
    scorecard_count: int
    tradeoff_count: int
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DecisionArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    session_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DecisionIntelligenceReport:
    timestamp: str
    candidate_count: int
    candidate_state_distribution: dict
    research_type_distribution: dict
    session_count: int
    session_state_distribution: dict
    framework_count: int
    scorecard_count: int
    tradeoff_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
