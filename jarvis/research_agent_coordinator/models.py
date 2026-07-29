"""Research Agent Execution Coordinator 자료형 (P12.3) — 연구 에이전트 조정. **조정·기록 전용.**

연구 작업을 수행하는 연구 에이전트를 조정한다(에이전트 배정·작업 위임·협업 추적·에이전트 진행·연구 핸드오프).
**외부 행위를 실행하지 않는다.** COORDINATE ≠ EXECUTION · ASSIGN ≠ AUTHORIZATION · HANDOFF ≠ DEPLOYMENT.
한 작업은 상충 소유자를 가질 수 없고, 핸드오프는 증거가 필요하며, 완료는 기록된 결과가 필요하다. 불변·
append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 rac_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 배정 생애주기(6) ──
A_CREATED = "CREATED"
A_ASSIGNED = "ASSIGNED"
A_IN_PROGRESS = "IN_PROGRESS"
A_HANDOFF = "HANDOFF"
A_REVIEW = "REVIEW"
A_COMPLETED = "COMPLETED"
ASSIGNMENT_STATES = (A_CREATED, A_ASSIGNED, A_IN_PROGRESS, A_HANDOFF, A_REVIEW, A_COMPLETED)

ALLOWED_TRANSITIONS = {
    A_CREATED: {A_ASSIGNED},
    A_ASSIGNED: {A_IN_PROGRESS},
    A_IN_PROGRESS: {A_HANDOFF, A_REVIEW},
    A_HANDOFF: {A_IN_PROGRESS, A_REVIEW},
    A_REVIEW: {A_COMPLETED, A_IN_PROGRESS},
    A_COMPLETED: set(),
}

# 활성(비완료) 상태
ACTIVE_STATES = (A_CREATED, A_ASSIGNED, A_IN_PROGRESS, A_HANDOFF, A_REVIEW)

# ── 금지(실행·배포·승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "DEPLOY", "ALLOCATE", "MODIFY_PERMISSION", "EXECUTE", "TRADE", "PLACE_ORDER",
    "PROMOTE_LIVE", "APPROVE_LIVE", "CHANGE_PERMISSION",
})


class ImmutableAgentError(Exception):
    """불변 에이전트 배정 레지스트리 위반."""


class ImmutableProgressError(Exception):
    """불변 진행 기록 위반."""


class ConflictingOwnerError(Exception):
    """한 작업에 상충 소유자 — 거부."""


class HandoffEvidenceError(Exception):
    """핸드오프 증거 누락 — 거부."""


class MissingResultError(Exception):
    """완료 시 기록된 결과 누락 — 거부."""


class IllegalAssignmentTransition(Exception):
    """유효하지 않은 배정 상태 전이 — 거부."""


class UnknownAssignmentError(Exception):
    """미등록 배정 참조."""


class UnknownAgentError(Exception):
    """미등록(미배정) 에이전트 참조."""


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


# ── 결정적 ID (AC* 스킴 — 기존 RC*/rco_ 계층과 구별) ──
def agent_registration_id(coordinator: str, agent: str) -> str:
    return "ACA:" + hashlib.sha1(input_digest(coordinator, agent).encode()).hexdigest()[:12]


def assignment_id(coordinator: str, task_ref: str) -> str:
    return "ACO:" + hashlib.sha1(input_digest(coordinator, task_ref).encode()).hexdigest()[:12]


def ownership_event_id(assignment: str, to_state: str, seq: int) -> str:
    return "ACV:" + hashlib.sha1(input_digest(assignment, to_state, seq).encode()).hexdigest()[:12]


def progress_id(assignment: str, seq: int) -> str:
    return "ACH:" + hashlib.sha1(input_digest(assignment, seq).encode()).hexdigest()[:12]


def handoff_id(assignment: str, seq: int) -> str:
    return "ACN:" + hashlib.sha1(input_digest(assignment, seq).encode()).hexdigest()[:12]


def collaboration_id(task_ref: str, seq: int) -> str:
    return "ACC:" + hashlib.sha1(input_digest(task_ref, seq).encode()).hexdigest()[:12]


def report_id(coordinator: str, scope: str, generated_at: str) -> str:
    return "ACG:" + hashlib.sha1(
        input_digest(coordinator, scope, generated_at).encode()).hexdigest()[:12]


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


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class AgentRegistrationRecord:
    agent_registration_id: str
    coordinator: str
    agent: str
    capability: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OwnershipEventRecord:
    ownership_event_id: str
    assignment_id: str
    coordinator: str
    task_ref: str
    agent: str
    from_state: str
    to_state: str
    result_ref: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProgressRecord:
    progress_id: str
    assignment_id: str
    agent: str
    percent: int
    note: str
    result_ref: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HandoffRecord:
    handoff_id: str
    assignment_id: str
    from_agent: str
    to_agent: str
    evidence_ref: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CollaborationRecord:
    collaboration_id: str
    task_ref: str
    agents: list
    winning_agent: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CoordinatorReportRecord:
    report_id: str
    coordinator: str
    scope: str
    assignment_count: int
    active_count: int
    completed_count: int
    handoff_count: int
    agent_count: int
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
class CoordinatorSummary:
    timestamp: str
    agent_registration_count: int
    ownership_event_count: int
    progress_count: int
    handoff_count: int
    collaboration_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
