"""Research Causal Intelligence 자료형 (P10.11) — 연구 객체 간 인과 관계 분석 전용.

P10.2~P10.8 연구 계층을 **READ ONLY** 로 소비해 변수·가설·관계연구·실험·증거·인과 그래프·리포트를
기록한다. **연구 증거일 뿐이다.** trading 실행·signal 생성·portfolio 배분·model 배포·자동 의사결정 없음.
VALIDATED ≠ CAUSALITY PROVEN · CAUSAL SCORE ≠ TRADING PERMISSION · RELATIONSHIP ≠ ACTION.
불변·append-only 해시체인·결정적. 물리 원장은 ci_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Hypothesis 생명주기 ──
DRAFT = "DRAFT"
TESTING = "TESTING"
EVIDENCED = "EVIDENCED"
REVIEWED = "REVIEWED"
ARCHIVED = "ARCHIVED"

HYPOTHESIS_STATES = (DRAFT, TESTING, EVIDENCED, REVIEWED, ARCHIVED)
HYPOTHESIS_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {TESTING},
    TESTING: {EVIDENCED},
    EVIDENCED: {REVIEWED},
    REVIEWED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Experiment 생명주기 ──
CREATED = "CREATED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
ANALYZED = "ANALYZED"

EXPERIMENT_STATES = (CREATED, RUNNING, COMPLETED, ANALYZED)
EXPERIMENT_TRANSITIONS = {
    "": {CREATED},
    CREATED: {RUNNING},
    RUNNING: {COMPLETED},
    COMPLETED: {ANALYZED},
    ANALYZED: set(),
}

# ── Graph 생명주기 ──
REGISTERED = "REGISTERED"
CONNECTED = "CONNECTED"
SNAPSHOTTED = "SNAPSHOTTED"

GRAPH_STATES = (REGISTERED, CONNECTED, SNAPSHOTTED)
GRAPH_TRANSITIONS = {
    "": {REGISTERED},
    REGISTERED: {CONNECTED},
    CONNECTED: {SNAPSHOTTED},
    SNAPSHOTTED: set(),
}

# ── 변수 유형(서술 라벨) ──
VAR_SIGNAL_RETURN = "signal_return"
VAR_VOLATILITY = "volatility"
VAR_LIQUIDITY = "liquidity"
VAR_FACTOR_EXPOSURE = "factor_exposure"
VAR_REGIME = "regime"
VAR_DATASET_QUALITY = "dataset_quality"
VARIABLE_TYPES = (VAR_SIGNAL_RETURN, VAR_VOLATILITY, VAR_LIQUIDITY, VAR_FACTOR_EXPOSURE,
                  VAR_REGIME, VAR_DATASET_QUALITY)

# ── 그래프 노드 유형 ──
NODE_VARIABLE = "VARIABLE"
NODE_SIGNAL = "SIGNAL"
NODE_FEATURE = "FEATURE"
NODE_STRATEGY = "STRATEGY"
NODE_PORTFOLIO = "PORTFOLIO"
NODE_REGIME = "REGIME"
NODE_DATASET = "DATASET"
NODE_TYPES = (NODE_VARIABLE, NODE_SIGNAL, NODE_FEATURE, NODE_STRATEGY, NODE_PORTFOLIO,
              NODE_REGIME, NODE_DATASET)

# ── 그래프 엣지 유형 ──
CAUSES = "CAUSES"
INFLUENCES = "INFLUENCES"
CORRELATED_WITH = "CORRELATED_WITH"
DEPENDS_ON = "DEPENDS_ON"
EXPLAINS = "EXPLAINS"
EDGE_TYPES = (CAUSES, INFLUENCES, CORRELATED_WITH, DEPENDS_ON, EXPLAINS)
# 방향성 엣지(순환 금지 검사 대상). CORRELATED_WITH 는 대칭 → 순환 검사 제외.
DIRECTED_EDGES = (CAUSES, INFLUENCES, DEPENDS_ON, EXPLAINS)

# ── 실험 방법 ──
CORRELATION_ANALYSIS = "correlation_analysis"
LAG_ANALYSIS = "lag_analysis"
REGIME_COMPARISON = "regime_comparison"
ABLATION_COMPARISON = "ablation_comparison"
INTERVENTION_SIMULATION = "intervention_simulation"   # 기록만 — 실제 개입 없음
EXPERIMENT_METHODS = (CORRELATION_ANALYSIS, LAG_ANALYSIS, REGIME_COMPARISON,
                      ABLATION_COMPARISON, INTERVENTION_SIMULATION)

# ── Causal support 라벨 ──
STRONG = "STRONG"
MODERATE = "MODERATE"
WEAK = "WEAK"
INCONCLUSIVE = "INCONCLUSIVE"

# 인과 분석 지표(합=1.0 가중, alt_warning 은 감점).
CAUSAL_WEIGHTS = {
    "relationship_strength": 0.35,
    "temporal_consistency": 0.25,
    "regime_stability": 0.20,
    "robustness": 0.20,
}

# ── Artifact 유형(계보) ──
ART_SOURCE = "SOURCE"
ART_VARIABLE = "VARIABLE"
ART_HYPOTHESIS = "HYPOTHESIS"
ART_EXPERIMENT = "EXPERIMENT"
ART_EVIDENCE = "EVIDENCE"
ART_GRAPH = "GRAPH"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableVariableError(Exception):
    """불변 변수 위반(동일 variable_id 내용 상이)."""


class ImmutableHypothesisError(Exception):
    """불변 가설 위반(동일 hypothesis_id 내용 상이)."""


class UnknownVariable(Exception):
    """미등록 변수 참조."""


class UnknownHypothesis(Exception):
    """미등록 가설 참조."""


class UnknownExperiment(Exception):
    """미등록 실험 참조."""


class CausalCycleError(Exception):
    """방향성 인과 엣지에 순환 유발 — 차단."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_hypothesis(frm: str, to: str) -> bool:
    return _can(HYPOTHESIS_TRANSITIONS, frm, to)


def can_transition_experiment(frm: str, to: str) -> bool:
    return _can(EXPERIMENT_TRANSITIONS, frm, to)


def can_transition_graph(frm: str, to: str) -> bool:
    return _can(GRAPH_TRANSITIONS, frm, to)


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
def variable_id(name: str, var_type: str, source_reference: str) -> str:
    return "CIV:" + hashlib.sha1(
        input_digest(name, var_type, source_reference).encode()).hexdigest()[:12]


def hypothesis_id(cause: str, effect: str, statement: str) -> str:
    return "CIH:" + hashlib.sha1(
        input_digest(cause, effect, statement).encode()).hexdigest()[:12]


def hypothesis_event_id(hid: str, frm: str, to: str) -> str:
    return "CHE:" + hashlib.sha1(input_digest(hid, frm, to).encode()).hexdigest()[:12]


def study_id(cause: str, edge_type: str, effect: str) -> str:
    return "CIR:" + hashlib.sha1(
        input_digest(cause, edge_type, effect).encode()).hexdigest()[:12]


def experiment_id(hypothesis_id_: str, method: str, inputs_hash: str) -> str:
    return "CIX:" + hashlib.sha1(
        input_digest(hypothesis_id_, method, inputs_hash).encode()).hexdigest()[:12]


def experiment_event_id(xid: str, frm: str, to: str) -> str:
    return "CXE:" + hashlib.sha1(input_digest(xid, frm, to).encode()).hexdigest()[:12]


def evidence_id(experiment_id_: str, metric: str) -> str:
    return "CIE:" + hashlib.sha1(
        input_digest(experiment_id_, metric).encode()).hexdigest()[:12]


def graph_id(name: str) -> str:
    return "CIG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def graph_event_id(gid: str, frm: str, to: str) -> str:
    return "CGE:" + hashlib.sha1(input_digest(gid, frm, to).encode()).hexdigest()[:12]


def report_id(hypothesis_id_: str) -> str:
    return "CIP:" + hashlib.sha1(input_digest(hypothesis_id_).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "CIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def graph_hash(nodes: list, edges: list) -> str:
    return _digest({"nodes": sorted(set(nodes or [])),
                    "edges": sorted({tuple(e) for e in (edges or [])})})


# ── 인과 분석(결정적) ──
def causal_support(metrics: dict) -> str:
    """인과 지표 → CAUSAL_SUPPORT (STRONG/MODERATE/WEAK/INCONCLUSIVE).

    **연구 증거 라벨일 뿐 — CAUSAL SCORE ≠ TRADING PERMISSION · RELATIONSHIP ≠ ACTION.**
    """
    score = causal_score(metrics)
    alt_warn = bool(metrics.get("alternative_explanation_warning", False))
    if alt_warn:
        # 대체 설명 경고 시 상한 제한(과신 방지).
        if score >= 0.5:
            return MODERATE
        if score >= 0.25:
            return WEAK
        return INCONCLUSIVE
    if score >= 0.75:
        return STRONG
    if score >= 0.5:
        return MODERATE
    if score >= 0.25:
        return WEAK
    return INCONCLUSIVE


def causal_score(metrics: dict) -> float:
    """가중 인과 근거 점수(0~1). 판단 지원 값 — 승인/실행 아님."""
    total = 0.0
    for key, wt in CAUSAL_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


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
class Variable:
    variable_id: str
    name: str
    var_type: str
    source_reference: str           # 외부 레이어 참조 문자열(READ ONLY)
    node_type: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HypothesisEvent:
    """인과 가설 등록·상태 전이 이벤트(이벤트 소싱). 정체성 불변."""
    event_id: str
    hypothesis_id: str
    cause_variable: str
    effect_variable: str
    statement: str
    mechanism: str
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
class RelationshipStudy:
    study_id: str
    cause: str
    effect: str
    edge_type: str                  # CAUSES | INFLUENCES | CORRELATED_WITH | DEPENDS_ON | EXPLAINS
    methodology: str
    dataset_reference: str
    period: str
    controls: list
    result: str                     # 서술 결과 — 자동 결론 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentEvent:
    event_id: str
    experiment_id: str
    hypothesis_id: str
    method: str
    inputs: dict
    controls: list
    results: dict
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
class Evidence:
    evidence_id: str
    experiment_id: str
    metric: str
    value: float
    interpretation: str             # 서술 — 자동 판단 아님
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphEvent:
    event_id: str
    graph_id: str
    name: str
    node_count: int
    edge_count: int
    node_distribution: dict
    edge_distribution: dict
    graph_hash: str
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
class CausalReport:
    report_id: str
    hypothesis_id: str
    cause_variable: str
    effect_variable: str
    metrics: dict
    causal_score: float
    causal_support: str             # STRONG | MODERATE | WEAK | INCONCLUSIVE
    evidence_count: int
    alternative_explanation_warning: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CausalArtifact:
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
class CausalSummary:
    timestamp: str
    variable_count: int
    hypothesis_count: int
    hypothesis_state_distribution: dict
    relationship_count: int
    edge_type_distribution: dict
    experiment_count: int
    experiment_state_distribution: dict
    evidence_count: int
    graph_count: int
    report_count: int
    support_distribution: dict

    def to_dict(self) -> dict:
        return asdict(self)
