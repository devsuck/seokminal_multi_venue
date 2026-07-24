"""Research Memory System 자료형 (P11.12) — 장기 연구 기억 계층. **기억 시스템 전용.**

연구 생태계 전반에서 생성된 역사적 연구 지식을 저장·조직·검색·분석한다(연구 이력 보존·실험 기억·실패 접근
추적·재사용 지식 발굴·방법론 회상·연구 맥락 검색·유사도 기반 기억 조회). **전략 실행·연구결과 수정·모델/거래
승인·배포·권한 변경·상위 데이터 변경을 하지 않는다.** 기억은 삭제·덮어쓰기·재작성이 없고, 새 정보는 새 기억
이벤트를 만든다. MEMORY ≠ EXECUTION · RECALL ≠ APPROVAL · PATTERN ≠ DEPLOYMENT. 불변·append-only·이벤트 소싱·
SHA256 해시체인·결정적. 물리 원장은 rmem_ 접두사(기존 rm_ 계층과 구별).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 기억 생애주기(5) ──
M_CREATED = "CREATED"
M_INDEXED = "INDEXED"
M_CONNECTED = "CONNECTED"
M_RETRIEVABLE = "RETRIEVABLE"
M_ARCHIVED = "ARCHIVED"
MEMORY_STATES = (M_CREATED, M_INDEXED, M_CONNECTED, M_RETRIEVABLE, M_ARCHIVED)

ALLOWED_TRANSITIONS = {
    M_CREATED: {M_INDEXED},
    M_INDEXED: {M_CONNECTED, M_RETRIEVABLE},
    M_CONNECTED: {M_CONNECTED, M_RETRIEVABLE},
    M_RETRIEVABLE: {M_RETRIEVABLE, M_ARCHIVED},
    M_ARCHIVED: set(),
}

# ── 기억 유형(9) ──
MEMORY_TYPES = (
    "EXPERIMENT_RESULT", "FAILED_APPROACH", "SUCCESS_PATTERN", "METHODOLOGY", "DATASET_INSIGHT",
    "STRATEGY_INSIGHT", "MODEL_INSIGHT", "AGENT_LEARNING", "PROCESS_IMPROVEMENT",
)

# ── 검색 모드 ──
MODE_EXACT = "EXACT"
MODE_SIMILARITY = "SIMILARITY"
MODE_LINEAGE = "LINEAGE"
MODE_RELATED = "RELATED"
MODE_HISTORICAL = "HISTORICAL"
SEARCH_MODES = (MODE_EXACT, MODE_SIMILARITY, MODE_LINEAGE, MODE_RELATED, MODE_HISTORICAL)

# ── 아티팩트(계보) 유형 ──
ART_MEMORY = "MEMORY"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"

# ── 금지(실행·승인·수정) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE", "APPROVE_STRATEGY", "APPROVE_MODEL",
    "MODIFY_STRATEGY", "MODIFY_MODEL", "CHANGE_PERMISSION", "CHANGE_CONFIG", "APPROVE", "ACTIVATE",
})


class ImmutableRegistryError(Exception):
    """불변 레지스트리 카탈로그 위반."""


class ImmutableMemoryError(Exception):
    """불변 기억(중복, 상이 맥락) 위반 — 재작성 금지."""


class ImmutableContextError(Exception):
    """불변 연구 맥락 위반."""


class ImmutableKnowledgeError(Exception):
    """불변 지식 엔트리 위반."""


class ImmutableExperimentError(Exception):
    """불변 실험 기억 위반."""


class ImmutableFailureError(Exception):
    """불변 실패 기억 위반."""


class ImmutablePatternError(Exception):
    """불변 성공 패턴 위반."""


class ImmutableAssociationError(Exception):
    """불변 기억 연관 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class IllegalMemoryTransition(Exception):
    """허용되지 않은 기억 상태 전이."""


class InvalidMemoryType(Exception):
    """미등록 기억 유형."""


class InvalidSearchMode(Exception):
    """미등록 검색 모드."""


class CircularAssociationError(Exception):
    """순환 기억 연관 — 거부."""


class DanglingReferenceError(Exception):
    """dangling 참조 — 거부."""


class MissingSourceError(Exception):
    """소스 참조 누락 — 거부."""


class UnknownMemoryError(Exception):
    """미등록 기억 참조."""


class UnknownRegistryError(Exception):
    """미등록 레지스트리 참조."""


# ── 해시(SHA256) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def context_digest(context) -> str:
    return _digest(context if context is not None else "")


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


# ── 결정적 ID (MS* 스킴 — 기존 RM* 계층과 구별) ──
def registry_id(memory: str) -> str:
    return "MSR:" + hashlib.sha1(input_digest(memory).encode()).hexdigest()[:12]


def memory_id(source_layer: str, source_id: str, memory_type: str, title: str) -> str:
    return "MSM:" + hashlib.sha1(
        input_digest(source_layer, source_id, memory_type, title).encode()).hexdigest()[:12]


def memory_event_id(memory: str, to_state: str, seq: int) -> str:
    return "MSV:" + hashlib.sha1(input_digest(memory, to_state, seq).encode()).hexdigest()[:12]


def knowledge_id(memory: str, summary: str) -> str:
    return "MSK:" + hashlib.sha1(input_digest(memory, summary).encode()).hexdigest()[:12]


def context_id(memory: str, context_key: str) -> str:
    return "MSC:" + hashlib.sha1(input_digest(memory, context_key).encode()).hexdigest()[:12]


def experiment_memory_id(memory: str, experiment_ref: str) -> str:
    return "MSX:" + hashlib.sha1(
        input_digest(memory, experiment_ref).encode()).hexdigest()[:12]


def failure_memory_id(memory: str, approach: str) -> str:
    return "MSF:" + hashlib.sha1(input_digest(memory, approach).encode()).hexdigest()[:12]


def success_pattern_id(memory: str, pattern: str) -> str:
    return "MSP:" + hashlib.sha1(input_digest(memory, pattern).encode()).hexdigest()[:12]


def association_id(memory_a: str, memory_b: str, relation: str) -> str:
    return "MSA:" + hashlib.sha1(
        input_digest(memory_a, memory_b, relation).encode()).hexdigest()[:12]


def snapshot_id(scope: str, taken_at: str) -> str:
    return "MSN:" + hashlib.sha1(input_digest(scope, taken_at).encode()).hexdigest()[:12]


def report_id(scope: str, generated_at: str) -> str:
    return "MSO:" + hashlib.sha1(input_digest(scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "MST:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def search_id(query: str, mode: str, seq: int) -> str:
    return "MSS:" + hashlib.sha1(input_digest(query, mode, seq).encode()).hexdigest()[:12]


# ── 결정적 분석/유사도 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def token_set(text: str) -> frozenset:
    """텍스트 → 소문자 토큰 집합(길이>=2, 결정적)."""
    return frozenset(t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2)


def jaccard(a: frozenset, b: frozenset) -> float:
    """자카드 유사도(결정적). 두 집합 모두 비면 0.0."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(inter / union, 6) if union else 0.0


def similarity(text_a: str, text_b: str) -> tuple:
    """설명 가능한 결정적 유사도. 반환 (score, shared_tokens)."""
    ta, tb = token_set(text_a), token_set(text_b)
    return jaccard(ta, tb), sorted(ta & tb)


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


def neighbors(edges: list, node: str) -> list:
    """무방향 인접(연관 그래프, 결정적)."""
    out: set = set()
    for a, b in edges:
        if a == node:
            out.add(b)
        elif b == node:
            out.add(a)
    return sorted(out)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class RegistryRecord:
    registry_id: str
    memory_id: str
    memory_type: str
    source_layer: str
    source_id: str
    title: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryEventRecord:
    memory_event_id: str
    memory_id: str
    memory_type: str
    source_layer: str
    source_id: str
    title: str
    original_context: str
    context_hash: str
    evidence_ref: str
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
class KnowledgeEntryRecord:
    knowledge_id: str
    memory_id: str
    summary: str
    tags: list
    reusable: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContextRecord:
    context_id: str
    memory_id: str
    context_key: str
    context_data: str
    context_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentMemoryRecord:
    experiment_memory_id: str
    memory_id: str
    experiment_ref: str
    outcome: str
    metrics: dict
    source_layer: str
    source_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureMemoryRecord:
    failure_memory_id: str
    memory_id: str
    approach: str
    reason: str
    recurrence: int
    source_layer: str
    source_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SuccessPatternRecord:
    success_pattern_id: str
    memory_id: str
    pattern: str
    conditions: str
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AssociationRecord:
    association_id: str
    memory_a: str
    memory_b: str
    relation: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    scope: str
    memory_count: int
    state_distribution: dict
    type_distribution: dict
    taken_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryReportRecord:
    report_id: str
    scope: str
    memory_count: int
    knowledge_count: int
    experiment_count: int
    failure_count: int
    pattern_count: int
    association_count: int
    retrievable_count: int
    type_distribution: dict
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
class SearchRecord:
    search_id: str
    query: str
    mode: str
    result_ids: list
    scores: dict
    explanation: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemorySummary:
    timestamp: str
    registry_count: int
    memory_event_count: int
    knowledge_count: int
    context_count: int
    experiment_count: int
    failure_count: int
    pattern_count: int
    association_count: int
    snapshot_count: int
    report_count: int
    artifact_count: int
    search_count: int

    def to_dict(self) -> dict:
        return asdict(self)
