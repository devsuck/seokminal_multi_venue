"""Cross-Agent Knowledge Sharing 자료형 (P11.8) — 연구 에이전트 간 지식 공유 계층. **공유·기록 전용.**

연구 지식·발견·교훈·재사용 아티팩트·구조화된 경험을 교환한다. **실행하지 않는다. 연구 결과를 바꾸지 않는다.
상위 원장을 수정하지 않는다. 배포를 승인하지 않는다.** SHARING ≠ EXECUTION · TRANSFER ≠ DEPLOYMENT · REUSE ≠
APPROVAL. 중복 불변 항목·순환 참조·dangling 참조·잘못된 계보는 거부된다. 모든 ID 는 결정적이며 재현 가능하다.
불변·append-only·이벤트 소싱·해시체인. 물리 원장은 ksh_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 지식 엔트리 생애주기 상태(6) ──
K_CREATED = "CREATED"
K_PUBLISHED = "PUBLISHED"
K_SHARED = "SHARED"
K_CONSUMED = "CONSUMED"
K_REUSED = "REUSED"
K_ARCHIVED = "ARCHIVED"
ENTRY_STATES = (K_CREATED, K_PUBLISHED, K_SHARED, K_CONSUMED, K_REUSED, K_ARCHIVED)

ALLOWED_TRANSITIONS = {
    K_CREATED: {K_PUBLISHED, K_ARCHIVED},
    K_PUBLISHED: {K_SHARED, K_ARCHIVED},
    K_SHARED: {K_CONSUMED, K_ARCHIVED},
    K_CONSUMED: {K_REUSED, K_ARCHIVED},
    K_REUSED: {K_ARCHIVED},
    K_ARCHIVED: set(),
}

# ── 지식 유형(13) ──
KT_OBSERVATION = "OBSERVATION"
KT_FINDING = "FINDING"
KT_EXPERIMENT = "EXPERIMENT"
KT_FEATURE = "FEATURE"
KT_SIGNAL = "SIGNAL"
KT_DATASET = "DATASET"
KT_STRATEGY = "STRATEGY"
KT_PORTFOLIO = "PORTFOLIO"
KT_RISK = "RISK"
KT_SIMULATION = "SIMULATION"
KT_REVIEW = "REVIEW"
KT_LESSON_LEARNED = "LESSON_LEARNED"
KT_BEST_PRACTICE = "BEST_PRACTICE"
KNOWLEDGE_TYPES = (KT_OBSERVATION, KT_FINDING, KT_EXPERIMENT, KT_FEATURE, KT_SIGNAL, KT_DATASET,
                   KT_STRATEGY, KT_PORTFOLIO, KT_RISK, KT_SIMULATION, KT_REVIEW, KT_LESSON_LEARNED,
                   KT_BEST_PRACTICE)

# ── 링크 종류 ──
LINK_TOPIC_PARENT = "TOPIC_PARENT"
LINK_TOPIC_RELATED = "TOPIC_RELATED"
LINK_ENTRY_RELATED = "ENTRY_RELATED"
LINK_ENTRY_TOPIC = "ENTRY_TOPIC"
LINK_TYPES = (LINK_TOPIC_PARENT, LINK_TOPIC_RELATED, LINK_ENTRY_RELATED, LINK_ENTRY_TOPIC)
# 순환 검사 대상(방향성) 링크 종류.
DIRECTIONAL_LINKS = frozenset({LINK_TOPIC_PARENT, LINK_ENTRY_RELATED})

# ── 아티팩트(계보) 유형 ──
ART_TOPIC = "TOPIC"
ART_ENTRY = "ENTRY"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"

# ── 금지(실행·거래·배포·승격·승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "BROKER", "MODIFY_PORTFOLIO", "ALLOCATE", "ALLOCATION",
    "PERMISSION", "CONFIG", "PROMOTE_STRATEGY", "PROMOTE_MODEL", "AUTO_APPROVE", "APPROVE",
    "ACTIVATE",
})


class ImmutableTopicError(Exception):
    """불변 토픽 위반."""


class ImmutableEntryError(Exception):
    """불변 지식 엔트리 위반(중복 불변 항목)."""


class ImmutableSourceError(Exception):
    """불변 소스 위반."""


class ImmutableLinkError(Exception):
    """불변 링크 위반."""


class ImmutableTransferError(Exception):
    """불변 전달 위반."""


class ImmutableRatingError(Exception):
    """불변 평가 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class InvalidKnowledgeType(Exception):
    """미등록 지식 유형."""


class InvalidLinkType(Exception):
    """미등록 링크 종류."""


class IllegalEntryTransition(Exception):
    """허용되지 않은 엔트리 상태 전이."""


class CircularReferenceError(Exception):
    """순환 참조 — 거부."""


class DanglingReferenceError(Exception):
    """dangling 참조 — 거부."""


class InvalidLineageError(Exception):
    """잘못된 계보 — 거부."""


class SelfReferenceError(Exception):
    """자기 참조 — 거부."""


class InvalidRating(Exception):
    """평가 범위 위반(1~5)."""


class UnknownRegistryError(Exception):
    """미등록 레지스트리 참조."""


class UnknownTopicError(Exception):
    """미등록 토픽 참조."""


class UnknownEntryError(Exception):
    """미등록 엔트리 참조."""


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


# ── 결정적 ID ──
def registry_id(name: str) -> str:
    return "KSG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def topic_id(name: str) -> str:
    return "KST:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def entry_id(topic: str, title: str, author: str) -> str:
    return "KSE:" + hashlib.sha1(input_digest(topic, title, author).encode()).hexdigest()[:12]


def entry_event_id(entry: str, to_state: str, seq: int) -> str:
    return "KEE:" + hashlib.sha1(input_digest(entry, to_state, seq).encode()).hexdigest()[:12]


def source_id(layer: str, ref: str) -> str:
    return "KSS:" + hashlib.sha1(input_digest(layer, ref).encode()).hexdigest()[:12]


def link_id(link_type: str, source: str, target: str) -> str:
    return "KSL:" + hashlib.sha1(
        input_digest(link_type, source, target).encode()).hexdigest()[:12]


def transfer_id(entry: str, from_agent: str, to_agent: str) -> str:
    return "KSX:" + hashlib.sha1(
        input_digest(entry, from_agent, to_agent).encode()).hexdigest()[:12]


def consumer_id(entry: str, agent: str) -> str:
    return "KSC:" + hashlib.sha1(input_digest(entry, agent).encode()).hexdigest()[:12]


def rating_id(entry: str, agent: str) -> str:
    return "KSR:" + hashlib.sha1(input_digest(entry, agent).encode()).hexdigest()[:12]


def snapshot_id(scope: str, taken_at: str) -> str:
    return "KSN:" + hashlib.sha1(input_digest(scope, taken_at).encode()).hexdigest()[:12]


def report_id(scope: str, generated_at: str) -> str:
    return "KSP:" + hashlib.sha1(input_digest(scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "KSA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def lineage_id(child_entry: str, parent_entry: str) -> str:
    return "KSD:" + hashlib.sha1(
        input_digest(child_entry, parent_entry).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


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


def reuse_score(consumers: int, transfers: int, ratings_avg: float, derived: int) -> float:
    """재사용 점수(0~1, 결정적): 소비자·전달·평점·파생 가중합. **REUSE ≠ APPROVAL.**"""
    c = min(1.0, float(max(0, consumers)) / 3.0)
    t = min(1.0, float(max(0, transfers)) / 3.0)
    r = min(1.0, max(0.0, float(ratings_avg)) / 5.0)
    d = min(1.0, float(max(0, derived)) / 2.0)
    return round(0.4 * c + 0.2 * t + 0.2 * r + 0.2 * d, 8)


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
class TopicRecord:
    topic_id: str
    registry_id: str
    name: str
    description: str
    parent_topic: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EntryEventRecord:
    entry_event_id: str
    entry_id: str
    topic_id: str
    title: str
    knowledge_type: str
    content: str
    author: str
    source_id: str
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
class SourceRecord:
    source_id: str
    layer: str
    ref: str
    description: str
    read_only: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LinkRecord:
    link_id: str
    link_type: str
    source_id: str
    target_id: str
    relation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TransferRecord:
    transfer_id: str
    entry_id: str
    from_agent: str
    to_agent: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConsumerRecord:
    consumer_id: str
    entry_id: str
    agent: str
    reused: bool
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RatingRecord:
    rating_id: str
    entry_id: str
    agent: str
    score: int
    comment: str
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
    entry_count: int
    topic_count: int
    transfer_count: int
    consumer_count: int
    state_distribution: dict
    type_distribution: dict
    content_digest: str
    taken_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeReportRecord:
    report_id: str
    scope: str
    entry_count: int
    topic_count: int
    transfer_count: int
    consumer_count: int
    rating_count: int
    avg_reuse_score: float
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
class LineageRecord:
    lineage_id: str
    child_entry: str
    parent_entry: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SharingSummary:
    timestamp: str
    registry_count: int
    topic_count: int
    entry_event_count: int
    source_count: int
    link_count: int
    transfer_count: int
    consumer_count: int
    rating_count: int
    snapshot_count: int
    report_count: int
    artifact_count: int
    lineage_count: int

    def to_dict(self) -> dict:
        return asdict(self)
