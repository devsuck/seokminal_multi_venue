"""Autonomous Research Manager 자료형 (P12.9) — 연구 워크플로 조정. **계획·추적·모니터링 전용.**

실행 관리자가 아니다 — 계획·추적·모니터링만. **거래 시작·주문 실행·모델 배포를 하지 않는다.** MANAGE ≠ EXECUTION ·
PLAN ≠ DEPLOYMENT · TRACK ≠ TRADING. 불변·append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 rmgr_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 계획 생애주기(6) ──
P_CREATED = "CREATED"
P_PLANNED = "PLANNED"
P_RUNNING = "RUNNING"
P_COMPLETED = "COMPLETED"
P_REVIEWED = "REVIEWED"
P_ARCHIVED = "ARCHIVED"
PLAN_STATES = (P_CREATED, P_PLANNED, P_RUNNING, P_COMPLETED, P_REVIEWED, P_ARCHIVED)

ALLOWED_TRANSITIONS = {
    P_CREATED: {P_PLANNED},
    P_PLANNED: {P_RUNNING},
    P_RUNNING: {P_RUNNING, P_COMPLETED},
    P_COMPLETED: {P_REVIEWED},
    P_REVIEWED: {P_ARCHIVED, P_RUNNING},
    P_ARCHIVED: set(),
}

# ── 작업 상태(필드) ──
TASK_STATES = ("PENDING", "IN_PROGRESS", "DONE", "BLOCKED")

# ── 아티팩트(계보) 유형 ──
ART_PLAN = "PLAN"
ART_TASK = "TASK"

# ── 금지(실행·거래·배포) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "START_TRADING", "RUN_ORDER", "PLACE_ORDER", "DEPLOY_MODEL", "DEPLOY", "EXECUTE", "TRADE",
    "ALLOCATE_CAPITAL", "PROMOTE_MODEL", "CHANGE_PERMISSION", "LIVE_TRADE",
})


class ImmutablePlanError(Exception):
    """불변 계획(중복) 위반."""


class ImmutableTaskError(Exception):
    """불변 작업 위반."""


class ImmutableDependencyError(Exception):
    """불변 의존 위반."""


class IllegalPlanTransition(Exception):
    """유효하지 않은 계획 상태 전이 — 거부."""


class CircularDependencyError(Exception):
    """순환 작업 의존성 — 거부."""


class DanglingDependencyError(Exception):
    """무효(dangling) 의존 — 거부."""


class UnknownPlanError(Exception):
    """미등록 계획 참조."""


class UnknownTaskError(Exception):
    """미등록 작업 참조."""


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


# ── 결정적 ID (RM* 스킴) ──
def plan_id(name: str) -> str:
    return "RMG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def plan_event_id(plan: str, to_state: str, seq: int) -> str:
    return "RMD:" + hashlib.sha1(input_digest(plan, to_state, seq).encode()).hexdigest()[:12]


def task_id(plan: str, name: str) -> str:
    return "RMT:" + hashlib.sha1(input_digest(plan, name).encode()).hexdigest()[:12]


def dependency_id(task: str, depends_on: str) -> str:
    return "RMP:" + hashlib.sha1(input_digest(task, depends_on).encode()).hexdigest()[:12]


def progress_id(task: str, seq: int) -> str:
    return "RMV:" + hashlib.sha1(input_digest(task, seq).encode()).hexdigest()[:12]


def report_id(plan: str, scope: str, generated_at: str) -> str:
    return "RMN:" + hashlib.sha1(
        input_digest(plan, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "RMF:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


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


def topological_order(nodes: list, edges: list) -> list:
    """의존(edge=(a depends_on b) → b before a) 위상 정렬(결정적). 순환이면 []."""
    node_set = set(nodes)
    adj: dict = {n: set() for n in node_set}
    indeg: dict = {n: 0 for n in node_set}
    for a, b in edges:
        if a in node_set and b in node_set and a not in adj[b]:
            adj[b].add(a)
            indeg[a] += 1
    ready = sorted([n for n in node_set if indeg[n] == 0])
    out: list = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in sorted(adj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort()
    return out if len(out) == len(node_set) else []


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class PlanEventRecord:
    plan_event_id: str
    plan_id: str
    name: str
    objective: str
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
    description: str
    owner: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyRecord:
    dependency_id: str
    task_id: str
    depends_on: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProgressRecord:
    progress_id: str
    task_id: str
    plan_id: str
    percent: int
    status: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StatusReportRecord:
    report_id: str
    plan_id: str
    scope: str
    task_count: int
    done_count: int
    dependency_count: int
    progress_count: int
    plan_state: str
    status_distribution: dict
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
class ManagerSummary:
    timestamp: str
    plan_event_count: int
    task_count: int
    dependency_count: int
    progress_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
