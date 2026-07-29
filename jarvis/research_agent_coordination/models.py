"""Autonomous Research Agent Coordination 자료형 (P26) — 연구 협업 조정 전용. **동작 없음.**

복수 연구 에이전트의 조정·역할 관리·작업 위임 기록·협업 이력·합의 추적·연구 토론 계보를 관리한다. **연구 협업만
관리한다.** 거래·주문·자본 배분·전략 배포·라이브 승인·권한 수정·자율 투자 결정 선택을 하지 않는다. CONSENSUS ≠
APPROVAL · CONSENSUS ≠ DEPLOYMENT · COORDINATION ≠ EXECUTION. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적.
물리 원장 racd_ 접두사. 상위 계층(P10~P25)은 READ ONLY. P10.6 Agent Governance 가 권한·정체성·행동 제한의 소유자.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 연구 세션 생애주기(5) — 이벤트 소싱 ──
S_CREATED = "CREATED"
S_ACTIVE = "ACTIVE"
S_DISCUSSING = "DISCUSSING"
S_CONCLUDED = "CONCLUDED"
S_ARCHIVED = "ARCHIVED"
SESSION_STATES = (S_CREATED, S_ACTIVE, S_DISCUSSING, S_CONCLUDED, S_ARCHIVED)
SESSION_TRANSITIONS = {
    S_CREATED: {S_ACTIVE},
    S_ACTIVE: {S_ACTIVE, S_DISCUSSING, S_CONCLUDED},
    S_DISCUSSING: {S_DISCUSSING, S_CONCLUDED, S_ACTIVE},
    S_CONCLUDED: {S_ARCHIVED, S_ACTIVE},
    S_ARCHIVED: set(),
}

# ── 연구 작업 생애주기(5) — 이벤트 소싱 ──
T_CREATED = "CREATED"
T_ASSIGNED = "ASSIGNED"
T_IN_PROGRESS = "IN_PROGRESS"
T_COMPLETED = "COMPLETED"
T_ARCHIVED = "ARCHIVED"
TASK_STATES = (T_CREATED, T_ASSIGNED, T_IN_PROGRESS, T_COMPLETED, T_ARCHIVED)
TASK_TRANSITIONS = {
    T_CREATED: {T_ASSIGNED},
    T_ASSIGNED: {T_ASSIGNED, T_IN_PROGRESS},
    T_IN_PROGRESS: {T_IN_PROGRESS, T_COMPLETED},
    T_COMPLETED: {T_ARCHIVED, T_IN_PROGRESS},
    T_ARCHIVED: set(),
}

# ── 역할 예시(자유 정의 가능, 권한 소유 아님) ──
ROLE_EXAMPLES = ("DATA_ANALYST", "VALIDATION_REVIEWER", "SIMULATION_ANALYST", "KNOWLEDGE_CURATOR",
                 "RESEARCH_COORDINATOR")
# ── 합의 판정(기록만) ──
CONSENSUS_VERDICTS = ("YES", "NO", "MIXED")

# ── 아티팩트 유형 ──
ART_AGENT = "AGENT"
ART_TEAM = "TEAM"
ART_SESSION = "SESSION"
ART_TASK = "TASK"
ART_MESSAGE = "MESSAGE"
ART_CONSENSUS = "CONSENSUS"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인·권한) 동사 — 역할 분리·자기승인 방지 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "CHANGE_PERMISSION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE",
    "APPROVE_LIVE", "SELF_APPROVE", "DEPLOY_OUTPUT", "MODIFY_GOVERNANCE", "MODIFY_PERMISSION",
    "SELECT_INVESTMENT",
})


class ImmutableAgentError(Exception):
    """불변 에이전트 정체성(중복 등록) 위반."""


class IllegalSessionTransition(Exception):
    """유효하지 않은 세션 전이 — 차단."""


class IllegalTaskTransition(Exception):
    """유효하지 않은 작업 전이 — 차단."""


class RoleSeparationError(Exception):
    """역할 분리 위반: 에이전트는 자기 권한 변경·자기 승인·배포·거버넌스 수정 불가."""


class TaskIsolationError(Exception):
    """작업 격리 위반: owner·objective 필수."""


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


def identity_hash(name, version, capabilities) -> str:
    return _digest({"name": name, "version": version, "capabilities": sorted(capabilities or [])})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (RC* 스킴) ──
def agent_id(name, version) -> str:
    return _id("RCA", name, version)


def role_id(name) -> str:
    return _id("RCO", name)


def team_id(objective) -> str:
    return _id("RCT", objective)


def session_id(objective) -> str:
    return _id("RCS", objective)


def session_event_id(sess, to, seq) -> str:
    return _id("RCE", sess, to, seq)


def task_id(sess, objective) -> str:
    return _id("RCK", sess, objective)


def task_event_id(task, to, seq) -> str:
    return _id("RCX", task, to, seq)


def message_id(sess, agent, seq) -> str:
    return _id("RCM", sess, agent, seq)


def consensus_id(sess, seq) -> str:
    return _id("RCC", sess, seq)


def report_id(scope, created_at) -> str:
    return _id("RCR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("RCF", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def contains_forbidden_action(actions) -> bool:
    """행동 목록에 금지 동사가 있으면 True(역할 분리·자기 승인 방지)."""
    return any(is_forbidden_verb(a) for a in (actions or []))


def can_session_transition(frm, to) -> bool:
    return to in SESSION_TRANSITIONS.get(frm, set())


def can_task_transition(frm, to) -> bool:
    return to in TASK_TRANSITIONS.get(frm, set())


def agreement_score(positions) -> float:
    """포지션(dict: agent→YES/NO/MIXED) → 합의 점수(0..1, 결정적). **점수만 — 자동 결정 없음.**"""
    if not positions:
        return 0.0
    vals = [str(v).strip().upper() for v in positions.values()]
    yes = sum(1 for v in vals if v == "YES")
    return round(yes / len(vals), 6)


def classify_consensus(score, positions=None) -> str:
    """합의 점수 → 판정(YES/NO/MIXED, 결정적). **기록만 — 승인/배포 트리거 없음.**"""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "MIXED"
    if s >= 1.0:
        return "YES"
    if s <= 0.0:
        return "NO"
    return "MIXED"


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


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    name: str
    version: str
    capabilities: list
    source_reference: str
    identity_hash: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RoleRecord:
    role_id: str
    name: str
    responsibility: str
    allowed_actions: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TeamRecord:
    team_id: str
    members: list
    objective: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionEventRecord:
    session_event_id: str
    session_id: str
    objective: str
    team_id: str
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
    session_id: str
    assigned_agent: str
    objective: str
    source: str
    dependencies: list
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
class MessageRecord:
    message_id: str
    session_id: str
    agent_id: str
    content: str
    refs: list
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConsensusRecord:
    consensus_id: str
    session_id: str
    positions: dict
    agreement_score: float
    verdict: str
    summary: str
    is_decision: bool  # 항상 False — 기록만, 자동 결정/승인/배포 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CoordinationReportRecord:
    report_id: str
    scope: str
    agent_count: int
    role_count: int
    team_count: int
    session_count: int
    active_session_count: int
    task_count: int
    completed_task_count: int
    message_count: int
    consensus_count: int
    verdict_distribution: dict
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
class CoordinationSummary:
    timestamp: str
    agent_count: int
    role_count: int
    team_count: int
    session_event_count: int
    session_count: int
    task_event_count: int
    task_count: int
    message_count: int
    consensus_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
