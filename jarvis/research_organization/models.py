"""Autonomous Research Organization 자료형 (P11.13) — 조직 조정 계층. **조직 전용.**

연구 에이전트·프로세스·지식·의사결정 시스템이 구조화된 조직으로 어떻게 조정되는지를 관리한다(연구 팀 구조·
에이전트 역할·책임 매핑·워크플로 소유·조정 정책·조직 상태 추적·연구 운영 투명성). **거래 실행·전략 배포·
라이브 승인·자본 배분·모델/전략 수정·권한 변경·자율 실행 인가를 하지 않는다.** 건강 지표는 분석 전용 —
자동 재배정·자동 승인·자동 실행을 유발하지 않는다. ORGANIZATION ≠ EXECUTION · ROLE ≠ AUTHORIZATION ·
METRIC ≠ ACTION. 불변·append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 rorg_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 조직 생애주기(6) ──
O_CREATED = "CREATED"
O_CONFIGURED = "CONFIGURED"
O_ACTIVE = "ACTIVE"
O_COORDINATING = "COORDINATING"
O_REVIEWED = "REVIEWED"
O_ARCHIVED = "ARCHIVED"
ORG_STATES = (O_CREATED, O_CONFIGURED, O_ACTIVE, O_COORDINATING, O_REVIEWED, O_ARCHIVED)

ALLOWED_TRANSITIONS = {
    O_CREATED: {O_CONFIGURED},
    O_CONFIGURED: {O_CONFIGURED, O_ACTIVE},
    O_ACTIVE: {O_ACTIVE, O_COORDINATING},
    O_COORDINATING: {O_COORDINATING, O_REVIEWED},
    O_REVIEWED: {O_COORDINATING, O_ARCHIVED},
    O_ARCHIVED: set(),
}

# ── 연구 유닛 유형(7) ──
UNIT_TYPES = (
    "DATA_RESEARCH", "STRATEGY_RESEARCH", "MODEL_RESEARCH", "SIMULATION_RESEARCH",
    "KNOWLEDGE_RESEARCH", "REVIEW_RESEARCH", "INFRASTRUCTURE_RESEARCH",
)

# ── 에이전트 역할(6) ──
AGENT_ROLES = (
    "RESEARCHER", "ANALYST", "REVIEWER", "COORDINATOR", "KNOWLEDGE_MANAGER", "QUALITY_AUDITOR",
)

# ── 책임 생애주기 상태(필드) ──
RESP_DEFINED = "DEFINED"
RESP_ACTIVE = "ACTIVE"
RESP_RETIRED = "RETIRED"
RESP_STATES = (RESP_DEFINED, RESP_ACTIVE, RESP_RETIRED)

# ── 아티팩트(계보) 유형 ──
ART_ORG = "ORG"
ART_UNIT = "UNIT"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"

# ── 금지(실행·승인·수정) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE", "APPROVE_TRADING", "APPROVE_MODEL",
    "MODIFY_STRATEGY", "MODIFY_MODEL", "CHANGE_PERMISSION", "CHANGE_CONFIG", "APPROVE", "ACTIVATE",
    "AUTHORIZE_EXECUTION", "REASSIGN",
})


class ImmutableOrganizationError(Exception):
    """불변 조직(중복, 상이 mandate) 위반."""


class ImmutableUnitError(Exception):
    """불변 연구 유닛 위반."""


class ImmutableTeamError(Exception):
    """불변 연구 팀 위반."""


class ImmutableRoleError(Exception):
    """불변 역할 배정 위반."""


class ImmutableResponsibilityError(Exception):
    """불변 책임 위반."""


class ImmutableWorkflowError(Exception):
    """불변 워크플로 소유 위반."""


class ImmutablePolicyError(Exception):
    """불변 조정 정책 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class IllegalOrgTransition(Exception):
    """허용되지 않은 조직 상태 전이(unauthorized transition)."""


class InvalidUnitType(Exception):
    """미등록 연구 유닛 유형."""


class InvalidAgentRole(Exception):
    """미등록 에이전트 역할."""


class CircularDependencyError(Exception):
    """순환 워크플로 의존성 — 거부."""


class DanglingReferenceError(Exception):
    """dangling 참조 — 거부."""


class MissingOwnerError(Exception):
    """소유자 누락 — 거부."""


class UnknownOrganizationError(Exception):
    """미등록 조직 참조."""


class UnknownUnitError(Exception):
    """미등록 유닛 참조."""


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


# ── 결정적 ID (RO* 스킴) ──
def org_id(name: str) -> str:
    return "ROG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def org_event_id(org: str, to_state: str, seq: int) -> str:
    return "ROV:" + hashlib.sha1(input_digest(org, to_state, seq).encode()).hexdigest()[:12]


def unit_id(org: str, unit_type: str, name: str) -> str:
    return "ROU:" + hashlib.sha1(input_digest(org, unit_type, name).encode()).hexdigest()[:12]


def team_id(unit: str, name: str) -> str:
    return "ROT:" + hashlib.sha1(input_digest(unit, name).encode()).hexdigest()[:12]


def role_id(unit: str, agent: str, role: str) -> str:
    return "ROR:" + hashlib.sha1(input_digest(unit, agent, role).encode()).hexdigest()[:12]


def responsibility_id(org: str, owner: str, scope: str) -> str:
    return "ROB:" + hashlib.sha1(input_digest(org, owner, scope).encode()).hexdigest()[:12]


def workflow_id(org: str, workflow_name: str) -> str:
    return "ROK:" + hashlib.sha1(input_digest(org, workflow_name).encode()).hexdigest()[:12]


def policy_id(org: str, name: str) -> str:
    return "ROP:" + hashlib.sha1(input_digest(org, name).encode()).hexdigest()[:12]


def snapshot_id(org: str, scope: str, taken_at: str) -> str:
    return "RON:" + hashlib.sha1(input_digest(org, scope, taken_at).encode()).hexdigest()[:12]


def report_id(org: str, scope: str, generated_at: str) -> str:
    return "ROO:" + hashlib.sha1(
        input_digest(org, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "ROF:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


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


def ratio(numerator: int, denominator: int) -> float:
    """결정적 비율(0..1). 분모 0 이면 1.0(공집합은 완전)."""
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 6)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class OrgEventRecord:
    org_event_id: str
    org_id: str
    name: str
    mandate: str
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
class UnitRecord:
    unit_id: str
    org_id: str
    unit_type: str
    name: str
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TeamRecord:
    team_id: str
    unit_id: str
    org_id: str
    name: str
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RoleRecord:
    role_id: str
    org_id: str
    unit_id: str
    team_id: str
    agent: str
    role: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResponsibilityRecord:
    responsibility_id: str
    org_id: str
    owner: str
    scope: str
    input_sources: list
    expected_output: str
    evidence_reference: str
    lifecycle_state: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowOwnershipRecord:
    workflow_id: str
    org_id: str
    workflow_name: str
    owner_unit: str
    input_sources: list
    depends_on: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyRecord:
    policy_id: str
    org_id: str
    name: str
    policy_type: str
    rule: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    org_id: str
    scope: str
    org_state: str
    unit_count: int
    role_count: int
    unit_type_distribution: dict
    role_distribution: dict
    taken_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrgReportRecord:
    report_id: str
    org_id: str
    scope: str
    unit_count: int
    team_count: int
    role_count: int
    responsibility_count: int
    workflow_count: int
    policy_count: int
    health: dict
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
class OrgSummary:
    timestamp: str
    org_event_count: int
    unit_count: int
    team_count: int
    role_count: int
    responsibility_count: int
    workflow_count: int
    policy_count: int
    snapshot_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
