"""Autonomous Research Coordinator 자료형 (P11.7) — 다중 연구 에이전트 조율 계층. **조율·기록 전용.**

연구 태스크 배정·의존성 조율·진행 모니터링·워크로드 재분배·정체 탐지·조율 리포트를 수행한다.
**연구를 실행하지 않는다. 거래하지 않는다. 배포하지 않는다. 어떤 상위 상태도 변경하지 않는다.**
COORDINATION ≠ EXECUTION · ASSIGNMENT ≠ TRADE · REBALANCE ≠ DEPLOYMENT · REPORT ≠ APPROVAL. 순환 의존성은
거부되고 완료 태스크는 불변이며 태스크 결과·연구 결론은 결코 수정되지 않는다. 불변·append-only·해시체인·
이벤트 소싱. 물리 원장은 rco_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 플랜 생애주기 상태(8) ──
P_CREATED = "CREATED"
P_PLANNING = "PLANNING"
P_ASSIGNING = "ASSIGNING"
P_RUNNING = "RUNNING"
P_BLOCKED = "BLOCKED"
P_REBALANCING = "REBALANCING"
P_COMPLETED = "COMPLETED"
P_ARCHIVED = "ARCHIVED"
PLAN_STATES = (P_CREATED, P_PLANNING, P_ASSIGNING, P_RUNNING, P_BLOCKED, P_REBALANCING,
               P_COMPLETED, P_ARCHIVED)

ALLOWED_TRANSITIONS = {
    P_CREATED: {P_PLANNING},
    P_PLANNING: {P_ASSIGNING},
    P_ASSIGNING: {P_RUNNING},
    P_RUNNING: {P_BLOCKED, P_REBALANCING, P_COMPLETED},
    P_BLOCKED: {P_RUNNING, P_REBALANCING},
    P_REBALANCING: {P_RUNNING},
    P_COMPLETED: {P_ARCHIVED},
    P_ARCHIVED: set(),
}

# 태스크(배정) 편집이 불가한 종료 상태.
EDITABLE_PLAN_STATES = frozenset({P_CREATED, P_PLANNING, P_ASSIGNING, P_RUNNING, P_BLOCKED,
                                  P_REBALANCING})

# ── 태스크 상태(4) ──
T_ASSIGNED = "ASSIGNED"
T_IN_PROGRESS = "IN_PROGRESS"
T_BLOCKED = "BLOCKED"
T_COMPLETED = "COMPLETED"
TASK_STATES = (T_ASSIGNED, T_IN_PROGRESS, T_BLOCKED, T_COMPLETED)

ALLOWED_TASK_TRANSITIONS = {
    T_ASSIGNED: {T_IN_PROGRESS, T_BLOCKED, T_COMPLETED},
    T_IN_PROGRESS: {T_BLOCKED, T_COMPLETED},
    T_BLOCKED: {T_IN_PROGRESS, T_COMPLETED},
    T_COMPLETED: set(),
}

# ── 에스컬레이션 심각도 ──
SEV_INFO = "INFO"
SEV_WARNING = "WARNING"
SEV_CRITICAL = "CRITICAL"
SEVERITIES = (SEV_INFO, SEV_WARNING, SEV_CRITICAL)

# ── 조율 이벤트 종류 ──
EV_TASK_ASSIGNED = "TASK_ASSIGNED"
EV_TASK_REASSIGNED = "TASK_REASSIGNED"
EV_PROGRESS_UPDATED = "PROGRESS_UPDATED"
EV_BLOCKER_DETECTED = "BLOCKER_DETECTED"
EV_WORKLOAD_REBALANCED = "WORKLOAD_REBALANCED"
EV_ISSUE_ESCALATED = "ISSUE_ESCALATED"
EV_PLAN_TRANSITION = "PLAN_TRANSITION"
EV_DEPENDENCY_ADDED = "DEPENDENCY_ADDED"
EVENT_KINDS = (EV_TASK_ASSIGNED, EV_TASK_REASSIGNED, EV_PROGRESS_UPDATED, EV_BLOCKER_DETECTED,
               EV_WORKLOAD_REBALANCED, EV_ISSUE_ESCALATED, EV_PLAN_TRANSITION, EV_DEPENDENCY_ADDED)

# ── 아티팩트(계보) 유형 ──
ART_COORDINATOR = "COORDINATOR"
ART_PLAN = "PLAN"
ART_ASSIGNMENT = "ASSIGNMENT"
ART_REPORT = "REPORT"

# ── 금지(실행·거래·배포·승격) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "TRADE", "EXECUTE", "DEPLOY", "BROKER", "ALLOCATE", "ALLOCATION", "PERMISSION",
    "CONFIG", "PROMOTE_STRATEGY", "PROMOTE_MODEL", "RISK_MUTATION", "MODIFY_PORTFOLIO",
    "APPROVE", "ACTIVATE",
})


class ImmutableCoordinatorError(Exception):
    """불변 코디네이터 위반."""


class ImmutableDependencyError(Exception):
    """불변 의존성 위반."""


class ImmutableEscalationError(Exception):
    """불변 에스컬레이션 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class IllegalPlanTransition(Exception):
    """허용되지 않은 플랜 상태 전이."""


class IllegalTaskTransition(Exception):
    """허용되지 않은 태스크 상태 전이."""


class DependencyCycleError(Exception):
    """순환 의존성 — 거부(DAG 유지)."""


class SelfDependencyError(Exception):
    """자기 의존성 — 거부."""


class CompletedTaskError(Exception):
    """완료 태스크 변경 시도 — 불변."""


class InvalidSeverity(Exception):
    """미등록 심각도."""


class UnknownCoordinatorError(Exception):
    """미등록 코디네이터 참조."""


class UnknownPlanError(Exception):
    """미등록 플랜 참조."""


class UnknownTaskError(Exception):
    """미등록 태스크 참조."""


class PlanClosedError(Exception):
    """종료된 플랜(COMPLETED/ARCHIVED) 편집 시도."""


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
def coordinator_id(name: str) -> str:
    return "COO:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def plan_id(coordinator: str, name: str) -> str:
    return "COP:" + hashlib.sha1(input_digest(coordinator, name).encode()).hexdigest()[:12]


def plan_event_id(plan: str, to_state: str, seq: int) -> str:
    return "CPE:" + hashlib.sha1(input_digest(plan, to_state, seq).encode()).hexdigest()[:12]


def task_id(plan: str, task_name: str) -> str:
    return "COK:" + hashlib.sha1(input_digest(plan, task_name).encode()).hexdigest()[:12]


def assignment_event_id(task: str, seq: int) -> str:
    return "CAE:" + hashlib.sha1(input_digest(task, seq).encode()).hexdigest()[:12]


def dependency_id(plan: str, upstream: str, downstream: str) -> str:
    return "COD:" + hashlib.sha1(
        input_digest(plan, upstream, downstream).encode()).hexdigest()[:12]


def progress_id(task: str, seq: int) -> str:
    return "COG:" + hashlib.sha1(input_digest(task, seq).encode()).hexdigest()[:12]


def schedule_id(plan: str, seq: int) -> str:
    return "COS:" + hashlib.sha1(input_digest(plan, seq).encode()).hexdigest()[:12]


def workload_id(plan: str, seq: int) -> str:
    return "COW:" + hashlib.sha1(input_digest(plan, seq).encode()).hexdigest()[:12]


def event_id(plan: str, kind: str, seq: int) -> str:
    return "COE:" + hashlib.sha1(input_digest(plan, kind, seq).encode()).hexdigest()[:12]


def escalation_id(plan: str, task: str, seq: int) -> str:
    return "COX:" + hashlib.sha1(input_digest(plan, task, seq).encode()).hexdigest()[:12]


def report_id(plan: str, scope: str, generated_at: str) -> str:
    return "COR:" + hashlib.sha1(
        input_digest(plan, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "COT:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 그래프·조율 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition_plan(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def can_transition_task(frm: str, to: str) -> bool:
    return to in ALLOWED_TASK_TRANSITIONS.get(frm, set())


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
    """Kahn 위상정렬(결정적). 순환이면 None."""
    indeg = {n: 0 for n in nodes}
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
    """병렬 실행 가능 그룹(웨이브, 결정적). 순환이면 None."""
    indeg = {n: 0 for n in nodes}
    adj: dict = {n: [] for n in nodes}
    for u, d in edges:
        if u in indeg and d in indeg:
            adj[u].append(d)
            indeg[d] += 1
    remaining = set(nodes)
    waves: list = []
    while remaining:
        wave = sorted(n for n in remaining if indeg[n] == 0)
        if not wave:
            return None
        waves.append(wave)
        for n in wave:
            remaining.discard(n)
            for m in adj[n]:
                indeg[m] -= 1
    return waves


def workload_imbalance(distribution: dict) -> int:
    """워크로드 불균형(최대-최소 활성 태스크 수, 결정적)."""
    if not distribution:
        return 0
    vals = list(distribution.values())
    return max(vals) - min(vals)


def suggest_moves(distribution: dict) -> list:
    """과부하→저부하 재분배 제안(결정적, 실행 아님). 최대 (max-min)//2 만큼 균형."""
    if len(distribution) < 2:
        return []
    items = sorted(distribution.items(), key=lambda kv: (kv[1], kv[0]))
    low, high = items[0], items[-1]
    gap = high[1] - low[1]
    moves = []
    for _ in range(gap // 2):
        moves.append({"from": high[0], "to": low[0]})
    return moves


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class CoordinatorRecord:
    coordinator_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlanEventRecord:
    plan_event_id: str
    plan_id: str
    coordinator_id: str
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
class AssignmentEventRecord:
    assignment_event_id: str
    task_id: str
    plan_id: str
    task_name: str
    owner: str
    state: str
    is_reassignment: bool
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
class ProgressRecord:
    progress_id: str
    task_id: str
    plan_id: str
    percent: int
    state: str
    note: str
    recorded_at: str
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
class WorkloadRecord:
    workload_id: str
    plan_id: str
    distribution: dict
    imbalance: int
    suggested_moves: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CoordinationEventRecord:
    event_id: str
    plan_id: str
    kind: str
    reference: str
    detail: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EscalationRecord:
    escalation_id: str
    plan_id: str
    task_id: str
    reason: str
    severity: str
    resolved: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CompletionReportRecord:
    report_id: str
    plan_id: str
    coordinator_id: str
    scope: str
    lifecycle_state: str
    task_count: int
    completed_count: int
    blocked_count: int
    dependency_count: int
    is_dag: bool
    escalation_count: int
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
    plan_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CoordinatorSummary:
    timestamp: str
    coordinator_count: int
    plan_event_count: int
    assignment_event_count: int
    dependency_count: int
    progress_count: int
    schedule_count: int
    workload_count: int
    event_count: int
    escalation_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
