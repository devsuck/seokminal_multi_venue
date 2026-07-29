"""Research Memory & Experience 자료형 (P12.7) — 장기 연구 기억·경험. **기억·기록·검색 전용.**

성공/실패 실험·연구 교훈·검증 결과·에이전트 경험·의사결정 결과를 저장한다. **실행 능력 없음 — 기억·기록·검색만.**
MEMORY ≠ EXECUTION · SIMILARITY ≠ RECOMMENDATION · VALIDATED ≠ DEPLOYED. 유사도는 메타데이터 전용이며 자동 추천을
하지 않는다. 불변·append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 rxm_ 접두사(기존 rm_/rmem_ 계층과 구별).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 기억 생애주기(6) ──
M_CREATED = "CREATED"
M_RECORDED = "RECORDED"
M_INDEXED = "INDEXED"
M_RETRIEVABLE = "RETRIEVABLE"
M_REFERENCED = "REFERENCED"
M_ARCHIVED = "ARCHIVED"
MEMORY_STATES = (M_CREATED, M_RECORDED, M_INDEXED, M_RETRIEVABLE, M_REFERENCED, M_ARCHIVED)

ALLOWED_TRANSITIONS = {
    M_CREATED: {M_RECORDED},
    M_RECORDED: {M_INDEXED},
    M_INDEXED: {M_RETRIEVABLE},
    M_RETRIEVABLE: {M_REFERENCED, M_ARCHIVED},
    M_REFERENCED: {M_REFERENCED, M_RETRIEVABLE, M_ARCHIVED},
    M_ARCHIVED: set(),
}

# ── 기억 유형(7) ──
MEMORY_TYPES = ("SUCCESS_PATTERN", "FAILED_EXPERIMENT", "VALIDATION_RESULT", "DECISION_OUTCOME",
                "AGENT_EXPERIENCE", "SIMULATION_RESULT", "OPTIMIZATION_RESULT")

# ── 유사도 메타데이터 키(6) — 메타데이터 전용, 추천 아님 ──
SIM_KEYS = ("strategy", "dataset", "model", "experiment", "regime", "objective")

# ── 아티팩트(계보) 유형 ──
ART_MEMORY = "MEMORY"
ART_EPISODE = "EPISODE"
ART_SUMMARY = "SUMMARY"

# ── 금지(실행·배포·거래) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "TRADE", "ORDER", "EXECUTE", "DEPLOY", "ALLOCATE", "PROMOTE_MODEL", "PROMOTE", "PLACE_ORDER",
    "EXECUTE_TRADE", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "CHANGE_PERMISSION", "LIVE_TRADE",
    "RECOMMEND",
})


class ImmutableMemoryError(Exception):
    """불변 기억(중복·재작성) 위반."""


class ImmutableExperienceError(Exception):
    """불변 경험 기록 위반."""


class ImmutableFailureError(Exception):
    """불변 실패 기억 위반."""


class ImmutablePatternError(Exception):
    """불변 성공 패턴 위반."""


class ImmutableEpisodeError(Exception):
    """불변 에피소드 위반."""


class IllegalMemoryTransition(Exception):
    """유효하지 않은 기억 상태 전이 — 거부."""


class InvalidMemoryType(Exception):
    """미등록 기억 유형."""


class DanglingReferenceError(Exception):
    """dangling 참조 — 거부."""


class UnknownMemoryError(Exception):
    """미등록 기억 참조."""


class UnknownEpisodeError(Exception):
    """미등록 에피소드 참조."""


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


# ── 결정적 ID (RX* 스킴) ──
def memory_id(source_layer: str, source_ref: str, memory_type: str, title: str) -> str:
    return "RXM:" + hashlib.sha1(
        input_digest(source_layer, source_ref, memory_type, title).encode()).hexdigest()[:12]


def memory_event_id(memory: str, to_state: str, seq: int) -> str:
    return "RXV:" + hashlib.sha1(input_digest(memory, to_state, seq).encode()).hexdigest()[:12]


def experience_id(memory: str, subject: str) -> str:
    return "RXE:" + hashlib.sha1(input_digest(memory, subject).encode()).hexdigest()[:12]


def failure_id(memory: str, approach: str) -> str:
    return "RXF:" + hashlib.sha1(input_digest(memory, approach).encode()).hexdigest()[:12]


def pattern_id(memory: str, pattern: str) -> str:
    return "RXP:" + hashlib.sha1(input_digest(memory, pattern).encode()).hexdigest()[:12]


def episode_id(name: str) -> str:
    return "RXS:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def retrieval_id(query: str, mode: str, seq: int) -> str:
    return "RXR:" + hashlib.sha1(input_digest(query, mode, seq).encode()).hexdigest()[:12]


def summary_id(scope: str, scope_id: str, generated_at: str) -> str:
    return "RXG:" + hashlib.sha1(
        input_digest(scope, scope_id, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RXA:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석/유사도 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def metadata_similarity(meta_a: dict, meta_b: dict) -> tuple:
    """메타데이터 유사도(SIM_KEYS 일치 비율, 결정적). 반환 (score, matched_keys). **메타데이터 전용 — 추천 아님.**"""
    meta_a = meta_a or {}
    meta_b = meta_b or {}
    matched = []
    considered = 0
    for k in SIM_KEYS:
        va, vb = meta_a.get(k), meta_b.get(k)
        if va is None and vb is None:
            continue
        considered += 1
        if va is not None and va == vb:
            matched.append(k)
    score = round(len(matched) / considered, 6) if considered else 0.0
    return score, sorted(matched)


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def token_set(text: str) -> frozenset:
    return frozenset(t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return round(len(a & b) / union, 6) if union else 0.0


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
class MemoryEventRecord:
    memory_event_id: str
    memory_id: str
    memory_type: str
    source_layer: str
    source_ref: str
    title: str
    context: str
    context_hash: str
    metadata: dict
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
class ExperienceRecord:
    experience_id: str
    memory_id: str
    subject: str
    outcome: str
    lesson: str
    agent: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureRecord:
    failure_id: str
    memory_id: str
    approach: str
    reason: str
    recurrence: int
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    memory_id: str
    pattern: str
    conditions: str
    confidence: float
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeRecord:
    episode_id: str
    name: str
    description: str
    memory_refs: list
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
    mode: str
    filters: dict
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
class SummaryRecord:
    summary_id: str
    scope: str
    scope_id: str
    memory_count: int
    experience_count: int
    failure_count: int
    pattern_count: int
    type_distribution: dict
    state_distribution: dict
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
class MemorySummary:
    timestamp: str
    memory_event_count: int
    experience_count: int
    failure_count: int
    pattern_count: int
    episode_count: int
    retrieval_count: int
    summary_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
