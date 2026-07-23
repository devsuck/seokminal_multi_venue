"""Research Memory Intelligence 자료형 (P10.14) — 장기 연구 기억 보존·검색·연결 전용.

P10.5·P10.7·P10.8·P10.11·P10.12·P10.13 을 **READ ONLY** 로 소비해 성공 패턴·실패 실험·발견 인사이트·
재사용 방법론·연구 교훈·역사적 맥락을 기억으로 보존한다. **연구 실행·trading signal 생성·strategy 선택·
model 수정·deploy 없음.** MEMORY ≠ DECISION · RECALL ≠ APPROVAL · SIMILARITY ≠ VALIDATION.
불변·append-only 해시체인·결정적. 물리 원장은 rm_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Memory 생명주기 ──
STORED = "STORED"
CONNECTED = "CONNECTED"
RETRIEVED = "RETRIEVED"
ARCHIVED = "ARCHIVED"

MEMORY_STATES = (STORED, CONNECTED, RETRIEVED, ARCHIVED)
MEMORY_TRANSITIONS = {
    "": {STORED},
    STORED: {CONNECTED, RETRIEVED, ARCHIVED},
    CONNECTED: {RETRIEVED, ARCHIVED},
    RETRIEVED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Memory 유형 ──
LESSON = "LESSON"
FAILURE = "FAILURE"
PATTERN = "PATTERN"
METHOD = "METHOD"
INSIGHT = "INSIGHT"
MEMORY_TYPES = (LESSON, FAILURE, PATTERN, METHOD, INSIGHT)

# ── Memory Connection 관계 ──
SIMILAR_TO = "SIMILAR_TO"
DERIVED_FROM = "DERIVED_FROM"
CONTRADICTS = "CONTRADICTS"
SUPPORTS = "SUPPORTS"
REPEATS = "REPEATS"
RELATIONS = (SIMILAR_TO, DERIVED_FROM, CONTRADICTS, SUPPORTS, REPEATS)
# 방향성 관계(순환 금지). 대칭 관계는 순환 검사 제외.
DIRECTED_RELATIONS = (DERIVED_FROM,)
UNDIRECTED_RELATIONS = (SIMILAR_TO, SUPPORTS, REPEATS)  # 클러스터링 대상(대칭)

# ── Memory confidence 라벨 ──
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# ── Memory Analysis 가중치(positive 합=1.0; contradiction 감점) ──
MEMORY_WEIGHTS = {
    "historical_relevance": 0.30,
    "evidence_strength": 0.30,
    "recurrence_frequency": 0.20,
    "confidence": 0.20,
}

# ── Artifact 유형(계보) ──
ART_SOURCE = "SOURCE"
ART_MEMORY = "MEMORY"
ART_LESSON = "LESSON"
ART_PATTERN = "PATTERN"
ART_CONNECTION = "CONNECTION"
ART_RETRIEVAL = "RETRIEVAL"
ART_CLUSTER = "CLUSTER"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 기억 생명주기 전이."""


class ImmutableMemoryError(Exception):
    """불변 기억 위반."""


class ImmutableLessonError(Exception):
    """불변 교훈 위반."""


class ImmutablePatternError(Exception):
    """불변 패턴 위반."""


class UnknownMemory(Exception):
    """미등록 기억 참조."""


class InvalidConnection(Exception):
    """유효하지 않은 연결(미등록 기억/관계/순환)."""


def can_transition_memory(frm: str, to: str) -> bool:
    return to in MEMORY_TRANSITIONS.get(frm, set())


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


def payload_hash(payload) -> str:
    return _digest(payload)


# ── 결정적 ID ──
def memory_id(mem_type: str, source_reference: str, content_hash_: str) -> str:
    return "RMM:" + hashlib.sha1(
        input_digest(mem_type, source_reference, content_hash_).encode()).hexdigest()[:12]


def memory_event_id(mid: str, frm: str, to: str) -> str:
    return "RME:" + hashlib.sha1(input_digest(mid, frm, to).encode()).hexdigest()[:12]


def lesson_id(observation: str, cause: str) -> str:
    return "RML:" + hashlib.sha1(input_digest(observation, cause).encode()).hexdigest()[:12]


def pattern_id(name: str) -> str:
    return "RPT:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def connection_id(from_memory: str, relation: str, to_memory: str) -> str:
    return "RMC:" + hashlib.sha1(
        input_digest(from_memory, relation, to_memory).encode()).hexdigest()[:12]


def retrieval_id(query: str, matched: list) -> str:
    return "RMR:" + hashlib.sha1(
        input_digest(query, sorted(matched or [])).encode()).hexdigest()[:12]


def cluster_id(signature: str) -> str:
    return "RMK:" + hashlib.sha1(input_digest(signature).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "RMO:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RMA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 검색(유사도) ──
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set:
    return set(_TOKEN_RE.findall((text or "").lower()))


def similarity(text_a: str, text_b: str) -> float:
    """토큰 Jaccard 유사도(0~1, 결정적). **SIMILARITY ≠ VALIDATION.**"""
    ta, tb = tokenize(text_a), tokenize(text_b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return round(inter / union, 8) if union else 0.0


# ── Memory analysis(결정적) ──
def memory_score(metrics: dict) -> float:
    """positive 가중 - contradiction 감점 → 0~1. **MEMORY ≠ DECISION.**"""
    pos = 0.0
    for key, wt in MEMORY_WEIGHTS.items():
        pos += float(metrics.get(key, 0.0)) * float(wt)
    contradiction = float(metrics.get("contradiction_level", 0.0))
    return round(max(0.0, min(1.0, pos - 0.3 * contradiction)), 8)


def memory_confidence(metrics: dict) -> str:
    """기억 지표 → HIGH/MEDIUM/LOW. **RECALL ≠ APPROVAL.**"""
    s = memory_score(metrics)
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


def connected_components(nodes: list, edges: list) -> list:
    adj: dict = {n: set() for n in nodes}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen: set = set()
    comps: list = []
    for start in sorted(adj):
        if start in seen:
            continue
        stack = [start]
        comp: set = set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(adj.get(n, ()) - seen)
        comps.append(sorted(comp))
    return sorted(comps, key=lambda c: (-len(c), c))


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class MemoryEvent:
    """연구 기억 등록·상태 전이 이벤트(이벤트 소싱). memory 정체성 불변."""
    event_id: str
    memory_id: str
    mem_type: str
    source_reference: str
    content_hash: str
    searchable_text: str
    importance: float
    confidence: float
    embedding_dim: int
    embedding_tag: str
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
class ResearchLesson:
    lesson_id: str
    observation: str
    cause: str
    impact: str
    evidence_refs: list
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryPattern:
    pattern_id: str
    name: str
    description: str
    usage_refs: list
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryConnection:
    connection_id: str
    from_memory: str
    relation: str                   # SIMILAR_TO | DERIVED_FROM | CONTRADICTS | SUPPORTS | REPEATS
    to_memory: str
    weight: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalRecord:
    retrieval_id: str
    query: str
    matched_memories: list
    similarity_scores: dict
    top_similarity: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCluster:
    cluster_id: str
    name: str
    member_memories: list
    size: int
    cohesion: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryReport:
    report_id: str
    scope: str
    memory_count: int
    memory_type_distribution: dict
    memory_state_distribution: dict
    lesson_count: int
    pattern_count: int
    connection_count: int
    relation_distribution: dict
    retrieval_count: int
    cluster_count: int
    metrics: dict
    memory_score: float
    memory_confidence: str
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryArtifact:
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
class MemorySummary:
    timestamp: str
    memory_count: int
    memory_type_distribution: dict
    memory_state_distribution: dict
    lesson_count: int
    pattern_count: int
    connection_count: int
    relation_distribution: dict
    retrieval_count: int
    cluster_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
