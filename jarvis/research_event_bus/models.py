"""Research Event Bus 자료형 (P11.11) — 내부 연구 이벤트 통신 계층. **통신 인프라 전용.**

연구 컴포넌트가 연구 생애주기 이벤트를 통제·감사 가능·append-only 방식으로 발행·소비하게 한다(이벤트 등록·
발행·구독 추적·이력·워크플로 동기화·교차계층 관찰성). **거래 실행·배포·전략/모델 수정·자본 배분·권한 변경·
자동 승인을 하지 않는다.** EVENT ≠ EXECUTION · PUBLISH ≠ DEPLOY · ROUTE ≠ APPROVAL. 불변·append-only·이벤트
소싱·SHA256 해시체인. 물리 원장은 reb_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 이벤트 생애주기(5) ──
E_CREATED = "CREATED"
E_PUBLISHED = "PUBLISHED"
E_ROUTED = "ROUTED"
E_CONSUMED = "CONSUMED"
E_ARCHIVED = "ARCHIVED"
EVENT_STATES = (E_CREATED, E_PUBLISHED, E_ROUTED, E_CONSUMED, E_ARCHIVED)

ALLOWED_TRANSITIONS = {
    E_CREATED: {E_PUBLISHED},
    E_PUBLISHED: {E_ROUTED, E_CONSUMED, E_ARCHIVED},
    E_ROUTED: {E_ROUTED, E_CONSUMED, E_ARCHIVED},
    E_CONSUMED: {E_CONSUMED, E_ARCHIVED},
    E_ARCHIVED: set(),
}

# ── 이벤트 유형(10) ──
EVENT_TYPES = (
    "RESEARCH_STARTED", "EXPERIMENT_CREATED", "BACKTEST_COMPLETED", "VALIDATION_FINISHED",
    "KNOWLEDGE_CREATED", "CONFLICT_DETECTED", "DECISION_RECORDED", "IMPROVEMENT_FOUND",
    "SIMULATION_COMPLETED", "REVIEW_COMPLETED",
)

# ── 소비자 활동 ──
ACT_DELIVERED = "DELIVERED"
ACT_CONSUMED = "CONSUMED"
CONSUMER_ACTIVITIES = (ACT_DELIVERED, ACT_CONSUMED)

# ── 아티팩트(계보) 유형 ──
ART_EVENT = "EVENT"
ART_STREAM = "STREAM"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"

# ── 금지(실행·승인·수정) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE", "MODIFY_STRATEGY", "MODIFY_MODEL",
    "CHANGE_PERMISSION", "CHANGE_CONFIG", "APPROVE", "ACTIVATE",
})


class ImmutableTypeError(Exception):
    """불변 이벤트 유형(중복 정의) 위반."""


class ImmutableSourceError(Exception):
    """불변 소스 등록 위반."""


class ImmutableStreamError(Exception):
    """불변 스트림 위반."""


class ImmutableEventError(Exception):
    """불변 이벤트(중복 발행, 상이 페이로드) 위반."""


class ImmutableSubscriberError(Exception):
    """불변 구독자 위반."""


class ImmutableRouteError(Exception):
    """불변 라우팅 규칙 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class IllegalEventTransition(Exception):
    """허용되지 않은 이벤트 상태 전이."""


class MissingParentError(Exception):
    """부모 이벤트 누락(dangling) — 거부."""


class CircularLineageError(Exception):
    """순환 이벤트 계보 — 거부."""


class UnauthorizedSourceError(Exception):
    """미등록·미인가 이벤트 소스 — 거부."""


class InvalidEventType(Exception):
    """미등록 이벤트 유형."""


class InvalidRoutingError(Exception):
    """잘못된 라우팅(미등록 유형·미등록 구독자)."""


class UnknownEventError(Exception):
    """미등록 이벤트 참조."""


class UnknownSubscriberError(Exception):
    """미등록 구독자 참조."""


class UnknownStreamError(Exception):
    """미등록 스트림 참조."""


# ── 해시(SHA256) ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def payload_digest(payload) -> str:
    """이벤트 페이로드 해시(원본 페이로드는 저장하지 않음 — 해시만 기록)."""
    return _digest(payload if payload is not None else {})


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


# ── 결정적 ID ──
def event_type_id(event_type: str) -> str:
    return "RBT:" + hashlib.sha1(input_digest(event_type).encode()).hexdigest()[:12]


def source_record_id(source_layer: str, source_id: str) -> str:
    return "RBO:" + hashlib.sha1(
        input_digest(source_layer, source_id).encode()).hexdigest()[:12]


def stream_id(name: str) -> str:
    return "RBS:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def event_id(source_layer: str, source_id: str, event_type: str, payload_hash: str) -> str:
    return "RBV:" + hashlib.sha1(
        input_digest(source_layer, source_id, event_type, payload_hash).encode()).hexdigest()[:12]


def event_lifecycle_id(event: str, to_state: str, seq: int) -> str:
    return "RBE:" + hashlib.sha1(input_digest(event, to_state, seq).encode()).hexdigest()[:12]


def subscriber_id(name: str, event_type: str) -> str:
    return "RBU:" + hashlib.sha1(input_digest(name, event_type).encode()).hexdigest()[:12]


def consumer_record_id(event: str, subscriber: str, activity: str, seq: int) -> str:
    return "RBC:" + hashlib.sha1(
        input_digest(event, subscriber, activity, seq).encode()).hexdigest()[:12]


def route_id(event_type: str, target_subscriber: str) -> str:
    return "RBR:" + hashlib.sha1(
        input_digest(event_type, target_subscriber).encode()).hexdigest()[:12]


def snapshot_id(scope: str, taken_at: str) -> str:
    return "RBN:" + hashlib.sha1(input_digest(scope, taken_at).encode()).hexdigest()[:12]


def report_id(scope: str, generated_at: str) -> str:
    return "RBP:" + hashlib.sha1(input_digest(scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RBA:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def lineage_id(event: str) -> str:
    return "RBL:" + hashlib.sha1(input_digest(event).encode()).hexdigest()[:12]


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


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class EventTypeRecord:
    event_type_id: str
    event_type: str
    description: str
    category: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SourceRecord:
    source_record_id: str
    source_layer: str
    source_id: str
    note: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StreamRecord:
    stream_id: str
    name: str
    event_type_filter: str
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EventLifecycleRecord:
    event_lifecycle_id: str
    event_id: str
    event_type: str
    source_layer: str
    source_id: str
    payload_hash: str
    parent_event: str
    metadata: dict
    authorized: bool
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
class SubscriberRecord:
    subscriber_id: str
    name: str
    event_type: str
    source_layer_filter: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConsumerRecord:
    consumer_record_id: str
    event_id: str
    subscriber: str
    activity: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RouteRecord:
    route_id: str
    event_type: str
    target_subscriber: str
    condition: str
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
    event_count: int
    state_distribution: dict
    type_distribution: dict
    taken_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EventReportRecord:
    report_id: str
    scope: str
    event_count: int
    published_count: int
    consumed_count: int
    archived_count: int
    subscriber_count: int
    route_count: int
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
    event_id: str
    parent_event: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EventBusSummary:
    timestamp: str
    type_count: int
    source_count: int
    stream_count: int
    event_lifecycle_count: int
    subscriber_count: int
    consumer_count: int
    route_count: int
    snapshot_count: int
    report_count: int
    artifact_count: int
    lineage_count: int

    def to_dict(self) -> dict:
        return asdict(self)
