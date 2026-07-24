"""Autonomous Research Task Planner 자료형 (P11.2) — AI 에이전트의 연구 워크플로 계획. **계획 전용.**

연구 목표(입력)로부터 연구 태스크 그래프(DAG, 출력)를 계획한다. 계획 생애주기: REQUESTED→PLANNED→RUNNING→
COMPLETED→REVIEWED. **계획만 한다 — 실행 없음. 자동 승인·자동 배포 없음.** RUNNING 은 관측 상태 라벨일 뿐,
본 계층은 어떤 태스크도 실행하지 않는다. PLAN ≠ EXECUTE · SCHEDULE ≠ DEPLOY · GRAPH ≠ APPROVAL. 계획은 불변·
append-only·해시체인. 물리 원장은 rtp_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 계획 생애주기 상태 ──
PLAN_REQUESTED = "REQUESTED"
PLAN_PLANNED = "PLANNED"
PLAN_RUNNING = "RUNNING"
PLAN_COMPLETED = "COMPLETED"
PLAN_REVIEWED = "REVIEWED"
PLAN_STATES = (PLAN_REQUESTED, PLAN_PLANNED, PLAN_RUNNING, PLAN_COMPLETED, PLAN_REVIEWED)

ALLOWED_PLAN_TRANSITIONS = {
    PLAN_REQUESTED: {PLAN_PLANNED},
    PLAN_PLANNED: {PLAN_RUNNING},
    PLAN_RUNNING: {PLAN_COMPLETED},
    PLAN_COMPLETED: {PLAN_REVIEWED},
    PLAN_REVIEWED: set(),
}

# 그래프 편집(태스크·의존성 추가)이 허용되는 상태 — REQUESTED 에서만(그 후 불변/동결).
EDITABLE_STATES = frozenset({PLAN_REQUESTED})

# ── 태스크 종류 ──
KIND_DATA = "DATA"
KIND_ANALYSIS = "ANALYSIS"
KIND_BACKTEST = "BACKTEST"
KIND_VALIDATION = "VALIDATION"
KIND_REVIEW = "REVIEW"
KIND_RESEARCH = "RESEARCH"
TASK_KINDS = (KIND_DATA, KIND_ANALYSIS, KIND_BACKTEST, KIND_VALIDATION, KIND_REVIEW, KIND_RESEARCH)

# ── 금지(자동 승인·자동 배포·실행) 동사 — 탐지용 ──
FORBIDDEN_PLANNER_VERBS = frozenset({
    "APPROVE", "AUTO_APPROVE", "DEPLOY", "AUTO_DEPLOY", "EXECUTE", "TRADE", "ALLOCATE",
    "ACTIVATE", "PROMOTE", "RELEASE",
})


class ImmutablePlanError(Exception):
    """불변 계획(정의) 위반."""


class ImmutableTaskError(Exception):
    """불변 태스크 위반."""


class ImmutableDependencyError(Exception):
    """불변 의존성 위반."""


class ImmutableScheduleError(Exception):
    """불변 스케줄 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class InvalidTaskKind(Exception):
    """미등록 태스크 종류."""


class IllegalPlanTransition(Exception):
    """허용되지 않은 계획 상태 전이."""


class PlanFrozenError(Exception):
    """동결된 계획 그래프 편집 시도(REQUESTED 이후 불변)."""


class DependencyCycleError(Exception):
    """의존성 추가로 순환 발생 — 거부(DAG 유지)."""


class SelfDependencyError(Exception):
    """자기 의존성 — 거부."""


class UnknownPlanError(Exception):
    """미등록 계획 참조."""


class UnknownTaskError(Exception):
    """미등록 태스크 참조."""


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
def plan_id(objective: str, requested_by: str, title: str) -> str:
    return "RTP:" + hashlib.sha1(
        input_digest(objective, requested_by, title).encode()).hexdigest()[:12]


def plan_event_id(plan: str, to_state: str) -> str:
    return "RPE:" + hashlib.sha1(input_digest(plan, to_state).encode()).hexdigest()[:12]


def task_id(plan: str, name: str) -> str:
    return "RTK:" + hashlib.sha1(input_digest(plan, name).encode()).hexdigest()[:12]


def dependency_id(plan: str, upstream: str, downstream: str) -> str:
    return "RTD:" + hashlib.sha1(
        input_digest(plan, upstream, downstream).encode()).hexdigest()[:12]


def schedule_id(plan: str) -> str:
    return "RTS:" + hashlib.sha1(input_digest(plan).encode()).hexdigest()[:12]


def report_id(plan: str, scope: str, generated_at: str) -> str:
    return "RTR:" + hashlib.sha1(
        input_digest(plan, scope, generated_at).encode()).hexdigest()[:12]


# ── 결정적 그래프 분석 ──
def is_forbidden_planner_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_PLANNER_VERBS


def can_transition_plan(frm: str, to: str) -> bool:
    return to in ALLOWED_PLAN_TRANSITIONS.get(frm, set())


def detect_cycle(edges: list) -> list:
    """방향 그래프(upstream→downstream) 순환 탐지(DFS, 결정적). 첫 순환 경로 또는 []."""
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


def topological_sort(nodes: list, edges: list) -> list | None:
    """Kahn 위상정렬(결정적, upstream 우선). 순환이면 None."""
    indeg: dict = {n: 0 for n in nodes}
    adj: dict = {n: [] for n in nodes}
    for u, d in edges:
        if u in indeg and d in indeg:
            adj[u].append(d)
            indeg[d] += 1
    ready = sorted(n for n in nodes if indeg[n] == 0)
    out: list = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in sorted(adj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort()
    return out if len(out) == len(nodes) else None


def build_waves(nodes: list, edges: list) -> list | None:
    """병렬 실행 가능 그룹(웨이브) 계산(결정적). 순환이면 None."""
    indeg: dict = {n: 0 for n in nodes}
    adj: dict = {n: [] for n in nodes}
    for u, d in edges:
        if u in indeg and d in indeg:
            adj[u].append(d)
            indeg[d] += 1
    remaining = set(nodes)
    waves: list = []
    processed: set = set()
    while remaining:
        wave = sorted(n for n in remaining if indeg[n] == 0)
        if not wave:
            return None  # 순환
        waves.append(wave)
        for n in wave:
            remaining.discard(n)
            processed.add(n)
            for m in adj[n]:
                indeg[m] -= 1
    return waves


def roots(nodes: list, edges: list) -> list:
    """진입 간선 없는 노드(의존성 없는 시작 태스크)."""
    has_incoming = {d for _, d in edges}
    return sorted(n for n in nodes if n not in has_incoming)


def leaves(nodes: list, edges: list) -> list:
    """진출 간선 없는 노드(최종 태스크)."""
    has_outgoing = {u for u, _ in edges}
    return sorted(n for n in nodes if n not in has_outgoing)


def ancestors(edges: list, node: str) -> list:
    """node 의 모든 상류(의존) 태스크(전이적, 결정적)."""
    rev: dict = {}
    for u, d in edges:
        rev.setdefault(d, set()).add(u)
    seen: set = set()
    stack = [node]
    while stack:
        x = stack.pop()
        for up in sorted(rev.get(x, ())):
            if up not in seen:
                seen.add(up)
                stack.append(up)
    return sorted(seen)


def descendants(edges: list, node: str) -> list:
    """node 에 의존하는 모든 하류 태스크(전이적, 결정적)."""
    adj: dict = {}
    for u, d in edges:
        adj.setdefault(u, set()).add(d)
    seen: set = set()
    stack = [node]
    while stack:
        x = stack.pop()
        for dn in sorted(adj.get(x, ())):
            if dn not in seen:
                seen.add(dn)
                stack.append(dn)
    return sorted(seen)


def redundant_edges(edges: list) -> list:
    """전이적으로 함의되는 잉여 의존성 간선 탐지(결정적)."""
    edgeset = set((u, d) for u, d in edges)
    out: list = []
    for u, d in sorted(edgeset):
        others = [(a, b) for (a, b) in edgeset if not (a == u and b == d)]
        if d in descendants(others, u):
            out.append((u, d))
    return sorted(out)


def lineage_chain(parent_map: dict, task: str) -> list:
    """task 의 계보(부모 체인, 결정적). dangling·순환은 중단."""
    out: list = []
    seen: set = set()
    cur = parent_map.get(task)
    while cur:
        if cur in seen:
            break
        seen.add(cur)
        out.append(cur)
        cur = parent_map.get(cur)
    return out


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class PlanEventRecord:
    plan_event_id: str
    plan_id: str
    objective: str
    title: str
    requested_by: str
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
class TaskRecord:
    task_id: str
    plan_id: str
    name: str
    kind: str
    objective: str
    parent_task: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyRecord:
    dependency_id: str
    plan_id: str
    upstream_task: str
    downstream_task: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleRecord:
    schedule_id: str
    plan_id: str
    order: list
    waves: list
    task_count: int
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlanReportRecord:
    report_id: str
    plan_id: str
    scope: str
    lifecycle_state: str
    task_count: int
    dependency_count: int
    is_dag: bool
    root_count: int
    leaf_count: int
    redundant_edge_count: int
    kind_distribution: dict
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlannerSummary:
    timestamp: str
    plan_event_count: int
    task_count: int
    dependency_count: int
    schedule_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
