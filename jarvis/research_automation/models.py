"""Research Automation Orchestration 자료형 (P22) — 연구 워크플로 자동화 조정·기록 전용. **실행 없음.**

기존 연구 컴포넌트를 조정(스케줄·의존·파이프라인·실행 기록)만 한다. **거래·주문·자본 배분·전략 배포·모델 수정·권한 변경·
라이브 승인을 하지 않는다.** ORCHESTRATE ≠ EXECUTE · COMPLETED ≠ VALIDATED · VALIDATED ≠ DEPLOYED · RECOMMENDED ≠
ENABLED. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 ra_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 워크플로 생애주기(5) ──
W_DRAFT = "DRAFT"
W_ACTIVE = "ACTIVE"
W_RUNNING = "RUNNING"
W_COMPLETED = "COMPLETED"
W_ARCHIVED = "ARCHIVED"
WORKFLOW_STATES = (W_DRAFT, W_ACTIVE, W_RUNNING, W_COMPLETED, W_ARCHIVED)
WORKFLOW_TRANSITIONS = {
    W_DRAFT: {W_ACTIVE},
    W_ACTIVE: {W_ACTIVE, W_RUNNING},
    W_RUNNING: {W_RUNNING, W_COMPLETED},
    W_COMPLETED: {W_ARCHIVED},
    W_ARCHIVED: set(),
}

# ── 파이프라인 생애주기(4) ──
P_CREATED = "CREATED"
P_READY = "READY"
P_EXECUTING = "EXECUTING"
P_FINISHED = "FINISHED"
PIPELINE_STATES = (P_CREATED, P_READY, P_EXECUTING, P_FINISHED)
PIPELINE_TRANSITIONS = {
    P_CREATED: {P_READY},
    P_READY: {P_EXECUTING},
    P_EXECUTING: {P_EXECUTING, P_FINISHED},
    P_FINISHED: set(),
}

# ── 작업 생애주기(6) ──
T_CREATED = "CREATED"
T_QUEUED = "QUEUED"
T_RUNNING = "RUNNING"
T_COMPLETED = "COMPLETED"
T_FAILED = "FAILED"
T_ARCHIVED = "ARCHIVED"
TASK_STATES = (T_CREATED, T_QUEUED, T_RUNNING, T_COMPLETED, T_FAILED, T_ARCHIVED)
TASK_TRANSITIONS = {
    T_CREATED: {T_QUEUED},
    T_QUEUED: {T_RUNNING},
    T_RUNNING: {T_COMPLETED, T_FAILED},
    T_COMPLETED: {T_ARCHIVED},
    T_FAILED: {T_QUEUED, T_ARCHIVED},
    T_ARCHIVED: set(),
}

# ── 이벤트 유형 ──
EVENT_TYPES = ("WORKFLOW_REGISTERED", "PIPELINE_DEFINED", "TASK_CREATED", "DEPENDENCY_ADDED",
               "RUN_STARTED", "TASK_COMPLETED", "TASK_FAILED", "RUN_FINISHED")

# ── 아티팩트 유형 ──
ART_WORKFLOW = "WORKFLOW"
ART_PIPELINE = "PIPELINE"
ART_TASK = "TASK"
ART_RUN = "RUN"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "PROMOTE_MODEL",
    "ENABLE_LIVE", "ACTIVATE_LIVE", "PORTFOLIO_MUTATION", "AUTO_SELECT_STRATEGY",
    "AUTO_APPROVE_ALPHA", "AUTO_DEPLOY_PORTFOLIO", "AUTO_CHANGE_PERMISSIONS", "EXECUTE", "TRADE",
    "DEPLOY", "ALLOCATE", "PROMOTE",
})


class ImmutableWorkflowError(Exception):
    """불변 워크플로(중복) 위반."""


class ImmutablePipelineError(Exception):
    """불변 파이프라인(중복) 위반."""


class ImmutableTaskError(Exception):
    """불변 작업(중복) 위반."""


class IllegalWorkflowTransition(Exception):
    """유효하지 않은 워크플로 전이 — 차단."""


class IllegalPipelineTransition(Exception):
    """유효하지 않은 파이프라인 전이 — 차단."""


class IllegalTaskTransition(Exception):
    """유효하지 않은 작업 전이 — 차단."""


class CircularDependencyError(Exception):
    """순환 의존성 — 거부."""


class DanglingDependencyError(Exception):
    """무효(dangling) 의존 — 거부."""


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


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


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (RA* 스킴, RAE 회피) ──
def workflow_id(name, version) -> str:
    return _id("RAW", name, version)


def workflow_event_id(wf, to, seq) -> str:
    return _id("RAK", wf, to, seq)


def pipeline_id(wf, name) -> str:
    return _id("RAP", wf, name)


def pipeline_event_id(pipe, to, seq) -> str:
    return _id("RAG", pipe, to, seq)


def task_id(pipe, name) -> str:
    return _id("RAT", pipe, name)


def task_event_id(task, to, seq) -> str:
    return _id("RAN", task, to, seq)


def run_id(pipe, seq) -> str:
    return _id("RAR", pipe, seq)


def dependency_id(parent, child) -> str:
    return _id("RAD", parent, child)


def event_id(scope, etype, seq) -> str:
    return _id("RAM", scope, etype, seq)


def report_id(pipe, scope, generated_at) -> str:
    return _id("RAF", pipe, scope, generated_at)


def artifact_id(atype, ref) -> str:
    return _id("RAA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_workflow_transition(frm, to) -> bool:
    return to in WORKFLOW_TRANSITIONS.get(frm, set())


def can_pipeline_transition(frm, to) -> bool:
    return to in PIPELINE_TRANSITIONS.get(frm, set())


def can_task_transition(frm, to) -> bool:
    return to in TASK_TRANSITIONS.get(frm, set())


def detect_cycle(edges) -> list:
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


def topological_order(nodes, edges) -> list:
    """의존(edge=(child depends_on parent) → parent before child) 위상 정렬(결정적). 순환이면 []."""
    node_set = set(nodes)
    adj: dict = {n: set() for n in node_set}
    indeg: dict = {n: 0 for n in node_set}
    for child, parent in edges:
        if child in node_set and parent in node_set and child not in adj[parent]:
            adj[parent].add(child)
            indeg[child] += 1
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
class WorkflowEventRecord:
    workflow_event_id: str
    workflow_id: str
    name: str
    version: str
    description: str
    source_layers: list
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
class PipelineEventRecord:
    pipeline_event_id: str
    pipeline_id: str
    workflow_id: str
    name: str
    steps: list
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
class TaskEventRecord:
    task_event_id: str
    task_id: str
    pipeline_id: str
    workflow_id: str
    task_type: str
    name: str
    input_reference: str
    from_state: str
    to_state: str
    results: dict
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyRecord:
    dependency_id: str
    parent_task: str
    child_task: str
    pipeline_id: str
    relation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    pipeline_id: str
    workflow_id: str
    status: str
    note: str
    started_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AutomationEventRecord:
    event_id: str
    scope_id: str
    event_type: str
    subject: str
    detail: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AutomationReportRecord:
    report_id: str
    pipeline_id: str
    workflow_id: str
    scope: str
    pipeline_state: str
    task_count: int
    task_status_distribution: dict
    dependency_count: int
    run_count: int
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
class AutomationSummary:
    timestamp: str
    workflow_event_count: int
    pipeline_event_count: int
    task_event_count: int
    dependency_count: int
    run_count: int
    event_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
