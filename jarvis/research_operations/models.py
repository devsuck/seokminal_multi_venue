"""Research Operations & Workflow Orchestration 자료형 (P18) — 워크플로 조정·계획·추적 전용. **실행 없음.**

연구 워크플로·작업·의존·실행 계획·런을 조정·기록만 한다. **거래·전략 배포·권한 변경·자동 실행·자동 승인을 하지 않는다.**
ORCHESTRATE ≠ EXECUTE · PLAN ≠ DEPLOYMENT · SCHEDULE ≠ TRADING. 불변·append-only·SHA256 해시체인·이벤트 소싱·
결정적. 물리 원장은 ro_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 워크플로 생애주기(8) — 상태 스킵 금지 ──
W_DRAFT = "DRAFT"
W_DEFINED = "DEFINED"
W_READY = "READY"
W_RUNNING = "RUNNING"
W_PAUSED = "PAUSED"
W_COMPLETED = "COMPLETED"
W_FAILED = "FAILED"
W_ARCHIVED = "ARCHIVED"
WORKFLOW_STATES = (W_DRAFT, W_DEFINED, W_READY, W_RUNNING, W_PAUSED, W_COMPLETED, W_FAILED,
                   W_ARCHIVED)

ALLOWED_WORKFLOW_TRANSITIONS = {
    W_DRAFT: {W_DEFINED},
    W_DEFINED: {W_DEFINED, W_READY},
    W_READY: {W_RUNNING},
    W_RUNNING: {W_RUNNING, W_PAUSED, W_COMPLETED, W_FAILED},
    W_PAUSED: {W_RUNNING, W_FAILED},
    W_COMPLETED: {W_ARCHIVED},
    W_FAILED: {W_READY, W_ARCHIVED},
    W_ARCHIVED: set(),
}

# ── 작업 생애주기(7) ──
T_CREATED = "CREATED"
T_QUEUED = "QUEUED"
T_RUNNING = "RUNNING"
T_COMPLETED = "COMPLETED"
T_FAILED = "FAILED"
T_BLOCKED = "BLOCKED"
T_CANCELLED = "CANCELLED"
TASK_STATES = (T_CREATED, T_QUEUED, T_RUNNING, T_COMPLETED, T_FAILED, T_BLOCKED, T_CANCELLED)

ALLOWED_TASK_TRANSITIONS = {
    T_CREATED: {T_QUEUED, T_BLOCKED, T_CANCELLED},
    T_QUEUED: {T_RUNNING, T_BLOCKED, T_CANCELLED},
    T_RUNNING: {T_COMPLETED, T_FAILED, T_BLOCKED},
    T_BLOCKED: {T_QUEUED, T_CANCELLED},
    T_FAILED: {T_QUEUED, T_CANCELLED},
    T_COMPLETED: set(),
    T_CANCELLED: set(),
}

# ── 이벤트 유형 ──
EVENT_TYPES = ("WORKFLOW_CREATED", "TASK_CREATED", "DEPENDENCY_ADDED", "RUN_STARTED",
               "TASK_COMPLETED", "TASK_FAILED", "WORKFLOW_COMPLETED", "WORKFLOW_FAILED")

# ── 아티팩트 유형 ──
ART_WORKFLOW = "WORKFLOW"
ART_TASK = "TASK"
ART_RUN = "RUN"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·자동조치) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "RUN_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY",
    "DEPLOY_MODEL", "DEPLOY", "PROMOTE_MODEL", "CHANGE_PERMISSION", "GRANT_PERMISSION",
    "AUTO_APPROVE", "AUTO_EXECUTE", "AUTO_DEPLOY", "AUTO_TRADE", "TRADE",
})


class ImmutableWorkflowError(Exception):
    """불변 워크플로(중복) 위반."""


class ImmutableTaskError(Exception):
    """불변 작업(중복) 위반."""


class IllegalWorkflowTransition(Exception):
    """유효하지 않은 워크플로 상태 전이 — 차단."""


class IllegalTaskTransition(Exception):
    """유효하지 않은 작업 상태 전이 — 차단."""


class CircularDependencyError(Exception):
    """순환 작업 의존성 — 거부."""


class DanglingDependencyError(Exception):
    """무효(dangling) 의존 — 거부."""


class UnknownWorkflowError(Exception):
    """미등록 워크플로 참조."""


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


# ── 결정적 ID (WO* 스킴) ──
def workflow_id(name: str) -> str:
    return "WOK:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def workflow_event_id(wf: str, to_state: str, seq: int) -> str:
    return "WOW:" + hashlib.sha1(input_digest(wf, to_state, seq).encode()).hexdigest()[:12]


def task_id(wf: str, name: str) -> str:
    return "WOT:" + hashlib.sha1(input_digest(wf, name).encode()).hexdigest()[:12]


def task_event_id(task: str, to_status: str, seq: int) -> str:
    return "WOS:" + hashlib.sha1(input_digest(task, to_status, seq).encode()).hexdigest()[:12]


def dependency_id(task: str, depends_on: str) -> str:
    return "WOD:" + hashlib.sha1(input_digest(task, depends_on).encode()).hexdigest()[:12]


def run_id(wf: str, seq: int) -> str:
    return "WOR:" + hashlib.sha1(input_digest(wf, seq).encode()).hexdigest()[:12]


def plan_id(wf: str, generated_at: str) -> str:
    return "WOP:" + hashlib.sha1(input_digest(wf, generated_at).encode()).hexdigest()[:12]


def event_id(wf: str, etype: str, seq: int) -> str:
    return "WOE:" + hashlib.sha1(input_digest(wf, etype, seq).encode()).hexdigest()[:12]


def report_id(wf: str, scope: str, generated_at: str) -> str:
    return "WON:" + hashlib.sha1(input_digest(wf, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(atype: str, ref: str) -> str:
    return "WOF:" + hashlib.sha1(input_digest(atype, ref).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_workflow_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_WORKFLOW_TRANSITIONS.get(frm, set())


def can_task_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TASK_TRANSITIONS.get(frm, set())


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
class WorkflowEventRecord:
    workflow_event_id: str
    workflow_id: str
    name: str
    description: str
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
    workflow_id: str
    name: str
    description: str
    owner: str
    priority: int
    from_status: str
    to_status: str
    note: str
    metadata: dict
    occurred_at: str
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
    workflow_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    workflow_id: str
    plan_id: str
    note: str
    started_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlanRecord:
    plan_id: str
    workflow_id: str
    ordered_tasks: list
    priorities: dict
    resource_estimate: float
    expected_duration: float
    dependency_ready: bool
    is_proposal: bool     # 항상 True — 제안일 뿐 자동 실행 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationEventRecord:
    event_id: str
    workflow_id: str
    event_type: str
    subject: str
    detail: str
    metadata: dict
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OperationReportRecord:
    report_id: str
    workflow_id: str
    scope: str
    workflow_state: str
    task_count: int
    task_status_distribution: dict
    dependency_count: int
    run_count: int
    event_count: int
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
class OperationsSummary:
    timestamp: str
    workflow_event_count: int
    task_event_count: int
    dependency_count: int
    run_count: int
    plan_count: int
    event_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
