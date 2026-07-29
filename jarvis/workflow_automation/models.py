"""Workflow Automation Layer 자료형 (P44) — 연구 워크플로 조율. **자율 실행 없음.**

연구 워크플로의 생애주기·태스크·의존성·검토 요청을 기록·조율한다. **자율 실행 아님 — 사람 승인 필수.**
WORKFLOW AUTOMATION ≠ AUTONOMOUS EXECUTION · Human approval remains required. 불변·append-only·SHA256 해시체인·
이벤트 소싱·결정적. 물리 원장 wf_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 워크플로 생애주기(5) — 이벤트 소싱 ──
W_CREATED = "CREATED"
W_PLANNED = "PLANNED"
W_RUNNING = "RUNNING"
W_COMPLETED = "COMPLETED"
W_ARCHIVED = "ARCHIVED"
WORKFLOW_STATES = (W_CREATED, W_PLANNED, W_RUNNING, W_COMPLETED, W_ARCHIVED)
WORKFLOW_TRANSITIONS = {
    W_CREATED: {W_PLANNED},
    W_PLANNED: {W_RUNNING},
    W_RUNNING: {W_RUNNING, W_COMPLETED},
    W_COMPLETED: {W_ARCHIVED},
    W_ARCHIVED: set(),
}

# ── 태스크 상태(5) — 이벤트 소싱. RUNNING = 사람이 진행 중으로 기록함(자동 실행 아님). ──
T_PENDING = "PENDING"
T_READY = "READY"
T_RUNNING = "RUNNING"
T_COMPLETED = "COMPLETED"
T_BLOCKED = "BLOCKED"
TASK_STATES = (T_PENDING, T_READY, T_RUNNING, T_COMPLETED, T_BLOCKED)
TASK_TRANSITIONS = {
    T_PENDING: {T_READY, T_BLOCKED},
    T_READY: {T_RUNNING, T_BLOCKED},
    T_RUNNING: {T_RUNNING, T_COMPLETED, T_BLOCKED},
    T_BLOCKED: {T_PENDING, T_READY},
    T_COMPLETED: set(),
}

# ── 검토 요청 상태 — 절대 자동 승인되지 않음. ──
REVIEW_PENDING = "PENDING_HUMAN_REVIEW"

# ── 태스크 종류 ──
TASK_KINDS = ("ANALYSIS", "DATA_PREP", "EXPERIMENT", "VALIDATION", "REPORTING", "REVIEW")

# ── 아티팩트 유형(계보) ──
ART_WORKFLOW = "WORKFLOW"
ART_TASK = "TASK"
ART_REPORT = "REPORT"

# ── 절대 금지(거래·실행·배포·배분·자율실행) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "AUTO_EXECUTE",
    "AUTO_RUN", "SELF_EXECUTE", "AUTO_APPROVE", "AUTO_DEPLOY",
})


class ImmutableWorkflowError(Exception):
    """불변 워크플로(중복 genesis) 위반."""


class IllegalWorkflowTransition(Exception):
    """유효하지 않은 워크플로 전이 — 차단."""


class IllegalTaskTransition(Exception):
    """유효하지 않은 태스크 전이 — 차단."""


class DependencyCycleError(Exception):
    """의존성 사이클 — 차단."""


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


def value_hash(*parts) -> str:
    return _digest(list(parts))


def artifact_content_hash(payload) -> str:
    return _digest({"payload": payload})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (WF* 스킴) ──
def workflow_id(name) -> str:
    return _id("WFW", name)


def workflow_event_id(wf, to, seq) -> str:
    return _id("WFE", wf, to, seq)


def task_id(wf, name) -> str:
    return _id("WFT", wf, name)


def task_event_id(tsk, to, seq) -> str:
    return _id("WFS", tsk, to, seq)


def dependency_id(wf, frm, to) -> str:
    return _id("WFD", wf, frm, to)


def approval_id(wf, stage, seq) -> str:
    return _id("WFP", wf, stage, seq)


def metadata_id(wf, key) -> str:
    return _id("WFM", wf, key)


def report_id(scope, created_at) -> str:
    return _id("WFR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("WFA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_workflow_transition(frm, to) -> bool:
    return to in WORKFLOW_TRANSITIONS.get(frm, set())


def can_task_transition(frm, to) -> bool:
    return to in TASK_TRANSITIONS.get(frm, set())


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


def detect_cycle_check(edges) -> bool:
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}

    def dfs(node) -> bool:
        color[node] = GRAY
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(nxt):
                return True
        color[node] = BLACK
        return False

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE and dfs(node):
            return True
    return False


def topological_order(nodes, edges):
    """의존성 위상 정렬(결정적). 사이클이면 None. edge (frm,to)=frm이 to에 의존."""
    graph: dict = {n: set() for n in nodes}
    indeg: dict = {n: 0 for n in nodes}
    for frm, to in edges:
        if frm in graph and to in graph and to not in graph[frm]:
            graph[frm].add(to)
            indeg[frm] += 1
    ready = sorted(n for n in nodes if indeg[n] == 0)
    order: list = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(nodes):
            if n in graph.get(m, set()):
                graph[m].discard(n)
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
        ready = sorted(ready)
    return order if len(order) == len(nodes) else None


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
    kind: str
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
class DependencyRecord:
    dependency_id: str
    workflow_id: str
    from_task: str
    to_task: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalRequestRecord:
    approval_id: str
    workflow_id: str
    stage: str
    status: str
    is_granted: bool
    requires_human_approval: bool
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowMetadataRecord:
    metadata_id: str
    workflow_id: str
    key: str
    value: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowReportRecord:
    report_id: str
    scope: str
    workflow_count: int
    running_workflow_count: int
    completed_workflow_count: int
    task_count: int
    dependency_count: int
    pending_review_count: int
    metadata_count: int
    state_distribution: dict
    task_status_distribution: dict
    requires_human_approval: bool
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
class WorkflowSummary:
    timestamp: str
    workflow_event_count: int
    workflow_count: int
    task_event_count: int
    task_count: int
    dependency_count: int
    approval_count: int
    metadata_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
