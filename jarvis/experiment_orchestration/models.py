"""Experiment Orchestration 자료형 (P31) — 실험 조정 기록 전용. **실험 실행 없음.**

연구 실험을 조정한다: 실험 계획·스케줄·의존성·실행 요청·실험 이력·실험 리포트. **실험을 실행하지 않는다 — 조정 기록만.
사람 승인이 항상 필요하다.** ORCHESTRATION ≠ EXECUTION · APPROVED ≠ EXECUTED · REQUEST ≠ RUN. 불변·append-only·
SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 exo_ 접두사. 상위 계층(P10~P30)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 실험 계획 생애주기(5) — 이벤트 소싱 ──
P_DRAFT = "DRAFT"
P_SCHEDULED = "SCHEDULED"
P_READY = "READY"
P_CONCLUDED = "CONCLUDED"
P_ARCHIVED = "ARCHIVED"
PLAN_STATES = (P_DRAFT, P_SCHEDULED, P_READY, P_CONCLUDED, P_ARCHIVED)
PLAN_TRANSITIONS = {
    P_DRAFT: {P_SCHEDULED},
    P_SCHEDULED: {P_SCHEDULED, P_READY},
    P_READY: {P_READY, P_CONCLUDED},
    P_CONCLUDED: {P_ARCHIVED, P_SCHEDULED},
    P_ARCHIVED: set(),
}

# ── 실행 요청 생애주기(4) — 이벤트 소싱, 사람 승인 필수, 실행 없음 ──
R_REQUESTED = "REQUESTED"
R_SUBMITTED = "SUBMITTED"
R_APPROVED = "APPROVED"
R_REJECTED = "REJECTED"
REQUEST_STATES = (R_REQUESTED, R_SUBMITTED, R_APPROVED, R_REJECTED)
REQUEST_TRANSITIONS = {
    R_REQUESTED: {R_SUBMITTED},
    R_SUBMITTED: {R_APPROVED, R_REJECTED, R_REQUESTED},
    R_APPROVED: set(),
    R_REJECTED: set(),
}

# ── 의존성 유형 ──
DEPENDENCY_TYPES = ("SEQUENTIAL", "DATA", "RESOURCE", "VALIDATION")
# ── 이력 결과(기록만) ──
HISTORY_OUTCOMES = ("RECORDED", "OBSERVED", "NOTED")

# ── 아티팩트 유형 ──
ART_PLAN = "PLAN"
ART_SCHEDULE = "SCHEDULE"
ART_REQUEST = "REQUEST"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·실험실행·배포·거래·승인자동) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "EXECUTE_EXPERIMENT", "RUN_EXPERIMENT", "AUTO_APPROVE", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE",
    "APPROVE_AUTO", "RUN", "LAUNCH_EXPERIMENT", "PROMOTE",
})


class ImmutablePlanError(Exception):
    """불변 계획(중복 genesis) 위반."""


class IllegalPlanTransition(Exception):
    """유효하지 않은 계획 전이 — 차단."""


class IllegalRequestTransition(Exception):
    """유효하지 않은 실행 요청 전이 — 차단."""


class ApproverRequired(Exception):
    """실행 요청 APPROVED/REJECTED 는 사람 승인자 필수 — 자동 승인 금지."""


class DependencyCycleError(Exception):
    """의존성 순환 — 차단."""


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


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (EO* 스킴) ──
def plan_id(name) -> str:
    return _id("EOP", name)


def plan_event_id(plan, to, seq) -> str:
    return _id("EOE", plan, to, seq)


def schedule_id(plan, seq) -> str:
    return _id("EOS", plan, seq)


def dependency_id(plan, depends_on) -> str:
    return _id("EOD", plan, depends_on)


def request_id(plan, seq) -> str:
    return _id("EOQ", plan, seq)


def request_event_id(req, to, seq) -> str:
    return _id("EOX", req, to, seq)


def history_id(plan, seq) -> str:
    return _id("EOH", plan, seq)


def report_id(scope, created_at) -> str:
    return _id("EOR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("EOA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_plan_transition(frm, to) -> bool:
    return to in PLAN_TRANSITIONS.get(frm, set())


def can_request_transition(frm, to) -> bool:
    return to in REQUEST_TRANSITIONS.get(frm, set())


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


def topological_order(nodes, edges) -> list:
    """의존성 위상 정렬(결정적). 순환이면 빈 리스트."""
    graph: dict = {n: set() for n in nodes}
    indeg: dict = {n: 0 for n in nodes}
    for a, b in edges:
        if b not in graph.get(a, set()):
            graph.setdefault(a, set()).add(b)
            indeg.setdefault(b, 0)
            indeg.setdefault(a, indeg.get(a, 0))
            indeg[b] += 1
    ready = sorted(n for n in indeg if indeg[n] == 0)
    order: list = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(graph.get(n, set())):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
                ready.sort()
    return order if len(order) == len(indeg) else []


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
class ScheduleRecord:
    schedule_id: str
    plan_id: str
    scheduled_for: str
    priority: str
    window: str
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
    depends_on: str
    dependency_type: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RequestEventRecord:
    request_event_id: str
    request_id: str
    plan_id: str
    requester: str
    approver: str
    is_executed: bool  # 항상 False — 요청·승인 기록만, 실험 실행 없음
    from_state: str
    to_state: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HistoryRecord:
    history_id: str
    plan_id: str
    phase: str
    outcome: str
    detail: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationReportRecord:
    report_id: str
    scope: str
    plan_count: int
    active_plan_count: int
    concluded_plan_count: int
    schedule_count: int
    dependency_count: int
    request_count: int
    approved_request_count: int
    history_count: int
    state_distribution: dict
    request_state_distribution: dict
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
class OrchestrationSummary:
    timestamp: str
    plan_event_count: int
    plan_count: int
    schedule_count: int
    dependency_count: int
    request_event_count: int
    request_count: int
    history_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
