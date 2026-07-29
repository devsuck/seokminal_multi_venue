"""Research Evolution Governance 자료형 (P10.16) — 연구 결과를 구조화된 학습 기록으로 전환. 저장·분석 전용.

이전 연구 산출물(성공/실패)을 READ ONLY 로 소비해 무엇이 통했는가·무엇이 실패했는가·왜 실패했는가·무엇을
개선할 수 있는가·어떤 후속 연구 질문이 남는가를 불변 학습 기록으로 남긴다. **strategy/signal/model/parameter
수정 없음·배포 없음·실행 트리거 없음.** LEARNING ≠ MODIFICATION · PROPOSAL ≠ APPROVAL · ACCEPTED ≠ DEPLOYMENT ·
IMPLEMENTED(record) ≠ PRODUCTION CHANGE. 불변·append-only 해시체인·결정적. 물리 원장은 ev_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Evolution Cycle 생명주기 ──
CREATED = "CREATED"
ANALYZED = "ANALYZED"
LEARNING_CAPTURED = "LEARNING_CAPTURED"
ARCHIVED = "ARCHIVED"

CYCLE_STATES = (CREATED, ANALYZED, LEARNING_CAPTURED, ARCHIVED)
CYCLE_TRANSITIONS = {
    "": {CREATED},
    CREATED: {ANALYZED},
    ANALYZED: {LEARNING_CAPTURED},
    LEARNING_CAPTURED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Improvement Proposal 생명주기 ──
# DRAFT→REVIEWING→ACCEPTED→IMPLEMENTED→ARCHIVED.
# IMPLEMENTED 는 '연구 상태 기록'일 뿐 프로덕션 변경·배포가 절대 아니다.
DRAFT = "DRAFT"
REVIEWING = "REVIEWING"
ACCEPTED = "ACCEPTED"
IMPLEMENTED = "IMPLEMENTED"
# ARCHIVED 공유

PROPOSAL_STATES = (DRAFT, REVIEWING, ACCEPTED, IMPLEMENTED, ARCHIVED)
PROPOSAL_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {REVIEWING, ARCHIVED},
    REVIEWING: {ACCEPTED, ARCHIVED},
    ACCEPTED: {IMPLEMENTED, ARCHIVED},
    IMPLEMENTED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 연구 객체 유형 ──
RT_STRATEGY = "STRATEGY"
RT_SIGNAL = "SIGNAL"
RT_MODEL = "MODEL"
RT_PORTFOLIO = "PORTFOLIO"
RT_EXPERIMENT = "EXPERIMENT"
RT_SIMULATION = "SIMULATION"
RT_HYPOTHESIS = "HYPOTHESIS"
RT_VALIDATION = "VALIDATION"
RESEARCH_TYPES = (RT_STRATEGY, RT_SIGNAL, RT_MODEL, RT_PORTFOLIO, RT_EXPERIMENT, RT_SIMULATION,
                  RT_HYPOTHESIS, RT_VALIDATION)

# ── 실패 패턴 범주 ──
F_OVERFITTING = "overfitting"
F_POOR_OOS = "poor_out_of_sample"
F_HIGH_TURNOVER = "high_turnover"
F_COST_SENSITIVE = "cost_sensitive"
F_REGIME_FAILURE = "regime_failure"
F_DATA_QUALITY = "data_quality_issue"
F_UNSTABLE_PARAM = "unstable_parameter"
F_LOW_REPRO = "low_reproducibility"
FAILURE_CATEGORIES = (F_OVERFITTING, F_POOR_OOS, F_HIGH_TURNOVER, F_COST_SENSITIVE,
                      F_REGIME_FAILURE, F_DATA_QUALITY, F_UNSTABLE_PARAM, F_LOW_REPRO)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

# ── 결과 라벨(iteration/analysis) ──
OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_PARTIAL = "PARTIAL"
OUTCOME_FAILURE = "FAILURE"
OUTCOME_INCONCLUSIVE = "INCONCLUSIVE"
OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_PARTIAL, OUTCOME_FAILURE, OUTCOME_INCONCLUSIVE)

# ── 학습 적용성(applicability) ──
AP_NARROW = "NARROW"
AP_MODERATE = "MODERATE"
AP_BROAD = "BROAD"
APPLICABILITIES = (AP_NARROW, AP_MODERATE, AP_BROAD)

# ── 계보 노드 유형 ──
# Research Object → Failure/Success Analysis → Learning Record → Improvement Proposal → Cycle
NODE_OBJECT = "RESEARCH_OBJECT"
NODE_FAILURE = "FAILURE"
NODE_LEARNING = "LEARNING"
NODE_PROPOSAL = "PROPOSAL"
NODE_CYCLE = "CYCLE"
NODE_ITERATION = "ITERATION"
NODE_TRANSFER = "TRANSFER"
NODE_TYPES = (NODE_OBJECT, NODE_FAILURE, NODE_LEARNING, NODE_PROPOSAL, NODE_CYCLE, NODE_ITERATION,
              NODE_TRANSFER)

# ── 계보 엣지 유형 ──
ANALYZED_AS = "ANALYZED_AS"      # object -> failure/analysis
LEARNED_FROM = "LEARNED_FROM"    # learning -> failure/object
PROPOSED_FROM = "PROPOSED_FROM"  # proposal -> failure/learning
FEEDS = "FEEDS"                  # learning/proposal -> cycle
TRANSFERS = "TRANSFERS"          # transfer -> learning/object
EDGE_TYPES = (ANALYZED_AS, LEARNED_FROM, PROPOSED_FROM, FEEDS, TRANSFERS)

# ── 학습 점수 가중치(합=1.0) — 정보용, 거래 점수 아님 ──
LEARNING_WEIGHTS = {
    "evidence_strength": 0.30,
    "reproducibility": 0.25,
    "applicability_breadth": 0.20,
    "confidence": 0.15,
    "future_value": 0.10,
}

# ── Artifact 유형(계보) ──
ART_OBJECT = "OBJECT"
ART_FAILURE = "FAILURE"
ART_LEARNING = "LEARNING"
ART_PROPOSAL = "PROPOSAL"
ART_CYCLE = "CYCLE"
ART_ITERATION = "ITERATION"
ART_TRANSFER = "TRANSFER"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableResearchObjectError(Exception):
    """불변 연구 객체 위반."""


class ImmutableFailureError(Exception):
    """불변 실패 패턴 위반."""


class ImmutableLearningError(Exception):
    """불변 학습 기록 위반."""


class ImmutableTransferError(Exception):
    """불변 지식 이전 기록 위반."""


class UnknownResearchObject(Exception):
    """미등록 연구 객체 참조."""


class UnknownCycle(Exception):
    """미등록 진화 사이클 참조."""


class UnknownProposal(Exception):
    """미등록 개선 제안 참조."""


class InvalidFailureCategory(Exception):
    """미등록 실패 범주."""


class InvalidLineageLink(Exception):
    """유효하지 않은 계보 링크(미등록 노드/엣지/순환)."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_cycle(frm: str, to: str) -> bool:
    return _can(CYCLE_TRANSITIONS, frm, to)


def can_transition_proposal(frm: str, to: str) -> bool:
    return _can(PROPOSAL_TRANSITIONS, frm, to)


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
def research_object_id(source_layer: str, source_reference: str) -> str:
    return "ERO:" + hashlib.sha1(
        input_digest(source_layer, source_reference).encode()).hexdigest()[:12]


def cycle_id(name: str) -> str:
    return "EVC:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def cycle_event_id(cid: str, frm: str, to: str) -> str:
    return "ECE:" + hashlib.sha1(input_digest(cid, frm, to).encode()).hexdigest()[:12]


def proposal_id(source_failure: str, hypothesis: str) -> str:
    return "EIP:" + hashlib.sha1(
        input_digest(source_failure, hypothesis).encode()).hexdigest()[:12]


def proposal_event_id(pid: str, frm: str, to: str) -> str:
    return "EPE:" + hashlib.sha1(input_digest(pid, frm, to).encode()).hexdigest()[:12]


def failure_id(category: str, pattern: str) -> str:
    return "EFP:" + hashlib.sha1(input_digest(category, pattern).encode()).hexdigest()[:12]


def iteration_id(cycle_ref: str, iteration_number: int) -> str:
    return "EIT:" + hashlib.sha1(
        input_digest(cycle_ref, int(iteration_number)).encode()).hexdigest()[:12]


def learning_id(source: str, lesson: str) -> str:
    return "ELR:" + hashlib.sha1(input_digest(source, lesson).encode()).hexdigest()[:12]


def transfer_id(from_context: str, to_context: str, knowledge: str) -> str:
    return "EKT:" + hashlib.sha1(
        input_digest(from_context, to_context, knowledge).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "ERP:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "EVA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수(결정적, 정보용) ──
def severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.0)


def learning_score(metrics: dict) -> float:
    """가중 학습 품질 점수(0~1). **LEARNING ≠ MODIFICATION — 거래 점수 아님.**"""
    total = 0.0
    for key, wt in LEARNING_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


def learning_confidence(metrics: dict) -> str:
    """학습 점수 → HIGH/MEDIUM/LOW. **정보용 — 자동 적용/배포 없음.**"""
    s = learning_score(metrics)
    if s >= 0.7:
        return "HIGH"
    if s >= 0.4:
        return "MEDIUM"
    return "LOW"


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
class ResearchObject:
    object_id: str
    source_layer: str
    source_reference: str
    research_type: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionCycleEvent:
    event_id: str
    cycle_id: str
    name: str
    source_objects: list
    observations: list
    lessons: list
    future_questions: list
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
class ImprovementProposalEvent:
    event_id: str
    proposal_id: str
    source_failure: str
    hypothesis: str
    expected_improvement: str
    evidence: list
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
    pattern: str
    severity: str
    evidence: list
    related_objects: list
    frequency: int
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IterationRecord:
    iteration_id: str
    cycle_ref: str
    iteration_number: int
    changes: list
    outcome: str
    notes: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearningRecord:
    learning_id: str
    source: str
    lesson: str
    confidence: float
    applicability: str
    lineage: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeTransferRecord:
    transfer_id: str
    from_context: str
    to_context: str
    knowledge: str
    applicability: str
    supporting_learning: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionReport:
    report_id: str
    scope: str
    object_count: int
    research_type_distribution: dict
    failure_count: int
    failure_category_distribution: dict
    cycle_count: int
    cycle_state_distribution: dict
    proposal_count: int
    proposal_state_distribution: dict
    learning_count: int
    transfer_count: int
    metrics: dict
    learning_score: float
    learning_confidence: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionArtifact:
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
class EvolutionSummary:
    timestamp: str
    object_count: int
    research_type_distribution: dict
    failure_count: int
    failure_category_distribution: dict
    cycle_count: int
    cycle_state_distribution: dict
    proposal_count: int
    proposal_state_distribution: dict
    iteration_count: int
    learning_count: int
    transfer_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
