"""Autonomous Experiment Scheduler 자료형 (P12.2) — 자율 연구 실험 스케줄링 지능. **스케줄·기록 전용.**

실험 큐·우선순위·스케줄링 규칙·자원 인식·의존 순서·실행 윈도 계획을 관리한다. **실험을 실행하지 않는다 — 스케줄·
기록만.** SCHEDULE ≠ EXECUTION · PLAN ≠ RUN · PRIORITY ≠ APPROVAL. 불변·append-only·이벤트 소싱·SHA256 해시체인·
결정적. 물리 원장은 aes_ 접두사. 무효 의존·순환 스케줄·중복 실행 요청·무단 우선순위 변경은 차단된다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 스케줄 요청 생애주기(7) ──
Q_REQUESTED = "REQUESTED"
Q_QUEUED = "QUEUED"
Q_PLANNED = "PLANNED"
Q_READY = "READY"
Q_SCHEDULED = "SCHEDULED"
Q_COMPLETED = "COMPLETED"
Q_ARCHIVED = "ARCHIVED"
SCHEDULE_STATES = (Q_REQUESTED, Q_QUEUED, Q_PLANNED, Q_READY, Q_SCHEDULED, Q_COMPLETED, Q_ARCHIVED)

ALLOWED_TRANSITIONS = {
    Q_REQUESTED: {Q_QUEUED},
    Q_QUEUED: {Q_PLANNED},
    Q_PLANNED: {Q_READY},
    Q_READY: {Q_SCHEDULED},
    Q_SCHEDULED: {Q_COMPLETED},
    Q_COMPLETED: {Q_ARCHIVED},
    Q_ARCHIVED: set(),
}

# 비종결(스케줄 가능) 상태
SCHEDULABLE_STATES = (Q_QUEUED, Q_PLANNED, Q_READY, Q_SCHEDULED)

# ── 금지(실행·배포·승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE", "APPROVE", "RUN_LIVE",
    "MODIFY_PERMISSION", "CHANGE_PERMISSION", "PLACE_ORDER", "EXECUTE_TRADE",
})


class ImmutableScheduleError(Exception):
    """불변 스케줄 레지스트리 위반."""


class ImmutablePolicyError(Exception):
    """불변 스케줄링 정책 위반."""


class DuplicateRequestError(Exception):
    """중복 실행 요청 — 거부."""


class PriorityChangeError(Exception):
    """무단 우선순위 변경 — 거부."""


class IllegalScheduleTransition(Exception):
    """유효하지 않은 스케줄 상태 전이 — 거부."""


class DanglingDependencyError(Exception):
    """무효(dangling) 의존 — 거부."""


class CircularScheduleError(Exception):
    """순환 스케줄 의존 — 거부."""


class UnknownScheduleError(Exception):
    """미등록 스케줄 참조."""


class UnknownRequestError(Exception):
    """미등록 실험 요청 참조."""


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


# ── 결정적 ID (ES* 스킴) ──
def schedule_id(name: str) -> str:
    return "ESG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def request_id(schedule: str, experiment_ref: str) -> str:
    return "ESQ:" + hashlib.sha1(
        input_digest(schedule, experiment_ref).encode()).hexdigest()[:12]


def schedule_event_id(request: str, to_state: str, seq: int) -> str:
    return "ESV:" + hashlib.sha1(input_digest(request, to_state, seq).encode()).hexdigest()[:12]


def policy_id(schedule: str, name: str) -> str:
    return "ESP:" + hashlib.sha1(input_digest(schedule, name).encode()).hexdigest()[:12]


def priority_id(request: str) -> str:
    return "ESR:" + hashlib.sha1(input_digest(request).encode()).hexdigest()[:12]


def dependency_id(request: str, depends_on: str) -> str:
    return "ESD:" + hashlib.sha1(input_digest(request, depends_on).encode()).hexdigest()[:12]


def snapshot_id(schedule: str, scope: str, taken_at: str) -> str:
    return "ESN:" + hashlib.sha1(
        input_digest(schedule, scope, taken_at).encode()).hexdigest()[:12]


def report_id(schedule: str, scope: str, generated_at: str) -> str:
    return "ESO:" + hashlib.sha1(
        input_digest(schedule, scope, generated_at).encode()).hexdigest()[:12]


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


def topological_order(nodes: list, edges: list, priority: dict = None) -> list:
    """의존(edge=(a depends_on b) → b before a) 위상 정렬. 결정적 tie-break: 우선순위 desc, id asc.

    순환이 있으면 [] 반환. priority: {node: int}.
    """
    priority = priority or {}
    node_set = set(nodes)
    adj: dict = {n: set() for n in node_set}   # b -> {a} (b 완료 후 a 가능)
    indeg: dict = {n: 0 for n in node_set}
    for a, b in edges:
        if a in node_set and b in node_set and a not in adj[b]:
            adj[b].add(a)
            indeg[a] += 1
    # 결정적 우선순위 큐(리스트): 우선순위 높은 것, id 작은 것 먼저
    ready = sorted([n for n in node_set if indeg[n] == 0],
                   key=lambda n: (-priority.get(n, 0), n))
    out: list = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in sorted(adj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort(key=lambda x: (-priority.get(x, 0), x))
    if len(out) != len(node_set):
        return []
    return out


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ScheduleRecord:
    schedule_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleEventRecord:
    schedule_event_id: str
    request_id: str
    schedule_id: str
    experiment_ref: str
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
class PolicyRecord:
    policy_id: str
    schedule_id: str
    name: str
    rule: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PriorityRecord:
    priority_id: str
    request_id: str
    priority: int
    rule: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyRecord:
    dependency_id: str
    request_id: str
    depends_on: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    schedule_id: str
    scope: str
    plan: list
    request_count: int
    state_distribution: dict
    taken_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleReportRecord:
    report_id: str
    schedule_id: str
    scope: str
    request_count: int
    scheduled_count: int
    completed_count: int
    dependency_count: int
    policy_count: int
    state_distribution: dict
    is_binding: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SchedulerSummary:
    timestamp: str
    schedule_count: int
    schedule_event_count: int
    policy_count: int
    priority_count: int
    dependency_count: int
    snapshot_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
