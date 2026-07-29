"""Research Memory & Continuous Learning 자료형 (P20) — 기억·분석 전용. **실행/학습적용 없음.**

과거 연구 경험·가설·성공/실패 실험·재사용 지식을 저장·검색·분석만 한다. **거래·라이브 신호·모델 수정·전략 배포·자본
배분·자동 승인을 하지 않는다.** REMEMBER ≠ EXECUTE · RETRIEVE ≠ RECOMMEND · CONFIDENCE ≠ APPROVAL. 불변·append-
only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 cl_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 기억 유형(10) ──
MEMORY_TYPES = ("EXPERIMENT", "STRATEGY", "SIGNAL", "FEATURE", "PORTFOLIO", "SIMULATION",
                "DECISION", "COLLABORATION", "FAILURE", "LESSON")

# ── 기억 생애주기(5) ──
M_CREATED = "CREATED"
M_INDEXED = "INDEXED"
M_RETRIEVABLE = "RETRIEVABLE"
M_REFERENCED = "REFERENCED"
M_ARCHIVED = "ARCHIVED"
MEMORY_STATES = (M_CREATED, M_INDEXED, M_RETRIEVABLE, M_REFERENCED, M_ARCHIVED)
MEMORY_TRANSITIONS = {
    M_CREATED: {M_INDEXED},
    M_INDEXED: {M_RETRIEVABLE},
    M_RETRIEVABLE: {M_RETRIEVABLE, M_REFERENCED, M_ARCHIVED},
    M_REFERENCED: {M_REFERENCED, M_RETRIEVABLE, M_ARCHIVED},
    M_ARCHIVED: set(),
}

# ── 교훈 생애주기(3) — 최종 교훈은 사람 검토 필요 ──
L_DRAFT = "DRAFT"
L_REVIEWED = "REVIEWED"
L_RECORDED = "RECORDED"
LESSON_STATES = (L_DRAFT, L_REVIEWED, L_RECORDED)
LESSON_TRANSITIONS = {
    L_DRAFT: {L_REVIEWED},
    L_REVIEWED: {L_RECORDED, L_DRAFT},
    L_RECORDED: set(),
}

# ── 실패 유형 ──
FAILURE_TYPES = ("OVERFITTING", "DATA_ISSUE", "LOW_ROBUSTNESS", "HIGH_COST", "REGIME_FAILURE",
                 "IMPLEMENTATION_ERROR")

# ── 아티팩트 유형 ──
ART_MEMORY = "MEMORY"
ART_EXPERIMENT = "EXPERIMENT"
ART_LESSON = "LESSON"
ART_REFERENCE = "REFERENCE"

# ── 절대 금지(실행·학습적용·자동조치) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "DEPLOY_STRATEGY", "ALLOCATE_CAPITAL", "MODIFY_MODEL",
    "AUTO_LEARN_MODEL", "AUTO_SELECT_STRATEGY", "TRAIN_MODEL", "OPTIMIZE_LIVE", "EXECUTE",
    "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE", "AUTO_APPROVE", "PROMOTE_MODEL",
})


class ImmutableRecordError(Exception):
    """불변 레코드(중복) 위반."""


class IllegalTransition(Exception):
    """유효하지 않은 상태 전이 — 차단."""


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


class ReviewerRequired(Exception):
    """사람 검토자 없이 교훈 확정 시도 — 차단(자동 승인 없음)."""


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


def metadata_hash(metadata) -> str:
    return _digest(metadata or {})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (CL* 스킴) ──
def memory_id(source_layer, source_reference) -> str:
    return _id("CLM", source_layer, source_reference)


def memory_event_id(mem, to, seq) -> str:
    return _id("CLL", mem, to, seq)


def experiment_memory_id(experiment_reference) -> str:
    return _id("CLE", experiment_reference)


def failure_id(failure_type, affected_research, seq) -> str:
    return _id("CLF", failure_type, affected_research, seq)


def pattern_id(pattern_type, description) -> str:
    return _id("CLP", pattern_type, description)


def lesson_id(lesson, context) -> str:
    return _id("CLS", lesson, context)


def lesson_event_id(les, to, seq) -> str:
    return _id("CLN", les, to, seq)


def retrieval_id(query_kind, query_hash, seq) -> str:
    return _id("CLR", query_kind, query_hash, seq)


def metric_id(name, seq) -> str:
    return _id("CLG", name, seq)


def artifact_id(atype, ref) -> str:
    return _id("CLA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_memory_transition(frm, to) -> bool:
    return to in MEMORY_TRANSITIONS.get(frm, set())


def can_lesson_transition(frm, to) -> bool:
    return to in LESSON_TRANSITIONS.get(frm, set())


def jaccard(a, b) -> float:
    """두 집합 자카드 유사도(결정적, 0..1)."""
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 1.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return round(inter / union, 6) if union else 0.0


def metadata_similarity(a, b) -> float:
    """메타데이터(dict) 유사도 — 동일 키·값 비율(결정적)."""
    ka, kb = set((a or {}).keys()), set((b or {}).keys())
    keys = ka | kb
    if not keys:
        return 1.0
    same = sum(1 for k in keys if (a or {}).get(k) == (b or {}).get(k))
    return round(same / len(keys), 6)


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
class MemoryEventRecord:
    memory_event_id: str
    memory_id: str
    memory_type: str
    source_layer: str
    source_reference: str
    summary: str
    metadata_hash: str
    tags: list
    from_state: str
    to_state: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentMemoryRecord:
    experiment_memory_id: str
    experiment_reference: str
    source_layer: str
    source_reference: str
    hypothesis: str
    dataset: str
    parameters: dict
    result_summary: str
    validation_status: str
    failure_reason: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureRecord:
    failure_id: str
    failure_type: str
    source_layer: str
    source_reference: str
    cause: str
    evidence: list
    affected_research: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SuccessPatternRecord:
    pattern_id: str
    pattern_type: str
    source_layer: str
    source_reference: str
    description: str
    supporting_records: list
    confidence: float       # 연구 메타데이터일 뿐 — 승인 아님
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LessonEventRecord:
    lesson_event_id: str
    lesson_id: str
    source_layer: str
    source_reference: str
    lesson: str
    context: str
    evidence: list
    related_experiments: list
    created_by: str
    reviewer: str           # 최종(RECORDED) 교훈은 검토자 필수
    from_state: str
    to_state: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalEventRecord:
    retrieval_id: str
    query_kind: str
    query: dict
    result_refs: list
    result_count: int
    source_layer: str
    source_reference: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearningMetricRecord:
    metric_id: str
    name: str
    value: float
    source_layer: str
    source_reference: str
    metadata: dict
    is_observation: bool    # 항상 True — 관찰일 뿐
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
    source_reference: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemorySummary:
    timestamp: str
    memory_event_count: int
    experiment_memory_count: int
    failure_count: int
    pattern_count: int
    lesson_event_count: int
    retrieval_count: int
    metric_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
