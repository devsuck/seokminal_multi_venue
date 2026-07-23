"""Agent Research Governance 자료형 (P10.6) — AI 연구 에이전트 관리·감사 전용.

AI Agent 는 **연구 보조자이며 실행 권한이 없다.** 에이전트 정체성·능력(메타데이터)·연구요청·실험제안·
행동감사·사람검토·연구예산·계보를 기록한다. **주문/전략배포/live trading/portfolio 변경/capital
allocation/permission 변경/risk threshold 변경/model promotion/execution 호출 없음.**
Agent VALIDATED ≠ APPROVED FOR TRADING · Research completed ≠ Deployment · Proposal accepted ≠
Execution permission. 불변·append-only 해시체인·결정적. 물리 원장은 arg_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Agent 생명주기 ──
REGISTERED = "REGISTERED"
ACTIVE = "ACTIVE"
SUSPENDED = "SUSPENDED"
RETIRED = "RETIRED"

AGENT_STATES = (REGISTERED, ACTIVE, SUSPENDED, RETIRED)
AGENT_TRANSITIONS = {
    "": {REGISTERED},
    REGISTERED: {ACTIVE, RETIRED},
    ACTIVE: {SUSPENDED, RETIRED},
    SUSPENDED: {ACTIVE, RETIRED},
    RETIRED: set(),
}

# ── Research Request 생명주기 ──
CREATED = "CREATED"
REVIEWING = "REVIEWING"
APPROVED = "APPROVED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
REJECTED = "REJECTED"

REQUEST_STATES = (CREATED, REVIEWING, APPROVED, RUNNING, COMPLETED, REJECTED)
REQUEST_TRANSITIONS = {
    "": {CREATED},
    CREATED: {REVIEWING, REJECTED},
    REVIEWING: {APPROVED, REJECTED},
    APPROVED: {RUNNING},
    RUNNING: {COMPLETED},
    COMPLETED: set(),
    REJECTED: set(),
}

# ── Experiment Proposal 생명주기 ──
DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
REVIEWED = "REVIEWED"
ACCEPTED = "ACCEPTED"
# REJECTED 공유

PROPOSAL_STATES = (DRAFT, SUBMITTED, REVIEWED, ACCEPTED, REJECTED)
PROPOSAL_TRANSITIONS = {
    "": {DRAFT},
    DRAFT: {SUBMITTED},
    SUBMITTED: {REVIEWED, REJECTED},
    REVIEWED: {ACCEPTED, REJECTED},
    ACCEPTED: set(),
    REJECTED: set(),
}

# ── Capability(메타데이터 — 실제 권한 부여 아님) ──
READ_DATA = "READ_DATA"
CREATE_HYPOTHESIS = "CREATE_HYPOTHESIS"
RUN_RESEARCH_SIMULATION = "RUN_RESEARCH_SIMULATION"
GENERATE_REPORT = "GENERATE_REPORT"
BUILD_GRAPH_QUERY = "BUILD_GRAPH_QUERY"
ALLOWED_CAPABILITIES = (READ_DATA, CREATE_HYPOTHESIS, RUN_RESEARCH_SIMULATION,
                        GENERATE_REPORT, BUILD_GRAPH_QUERY)

EXECUTE_TRADE = "EXECUTE_TRADE"
PLACE_ORDER = "PLACE_ORDER"
ALLOCATE_CAPITAL = "ALLOCATE_CAPITAL"
DEPLOY_STRATEGY = "DEPLOY_STRATEGY"
CHANGE_PERMISSION = "CHANGE_PERMISSION"
FORBIDDEN_CAPABILITIES = (EXECUTE_TRADE, PLACE_ORDER, ALLOCATE_CAPITAL, DEPLOY_STRATEGY,
                          CHANGE_PERMISSION)

# ── Action 유형 ──
ALLOWED_ACTIONS = ("CREATE_HYPOTHESIS", "QUERY_KNOWLEDGE_GRAPH", "GENERATE_REPORT",
                   "READ_DATA", "RUN_RESEARCH_SIMULATION", "BUILD_GRAPH_QUERY")
# 금지 행동은 기록은 가능하나 실행 불가 — 항상 BLOCKED 로 남는다.
FORBIDDEN_ACTIONS = ("EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY",
                     "CHANGE_PERMISSION", "PROMOTE_MODEL", "CHANGE_RISK_THRESHOLD",
                     "MODIFY_PORTFOLIO")
ACTION_BLOCKED = "BLOCKED_FORBIDDEN"

# ── Review 결정 ──
APPROVE = "APPROVE"
REJECT = "REJECT"
REQUEST_CHANGE = "REQUEST_CHANGE"
REVIEW_DECISIONS = (APPROVE, REJECT, REQUEST_CHANGE)

# ── Budget ──
BUDGET_LIMIT = "LIMIT"
BUDGET_USAGE = "USAGE"
KIND_EXPERIMENT = "experiment"
KIND_QUERY = "query"
BUDGET_OK = "OK"
BUDGET_BLOCKED = "BLOCKED"

# ── Artifact 유형(계보) ──
ART_AGENT = "AGENT"
ART_REQUEST = "REQUEST"
ART_PROPOSAL = "PROPOSAL"
ART_EXPERIMENT = "EXPERIMENT"
ART_VALIDATION = "VALIDATION"
ART_ARTIFACT = "ARTIFACT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableAgentError(Exception):
    """불변 에이전트 정체성 위반."""


class ImmutableRequestError(Exception):
    """불변 연구요청 위반."""


class ForbiddenCapability(Exception):
    """금지 능력 부여 시도 — 거부. 실행 권한은 부여할 수 없다."""


class HumanApprovalRequired(Exception):
    """사람 검토·승인 없이 수락 시도 — 거부. 자동 승인 금지."""


class UnknownProposal(Exception):
    """미존재 제안 참조."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_agent(frm: str, to: str) -> bool:
    return _can(AGENT_TRANSITIONS, frm, to)


def can_transition_request(frm: str, to: str) -> bool:
    return _can(REQUEST_TRANSITIONS, frm, to)


def can_transition_proposal(frm: str, to: str) -> bool:
    return _can(PROPOSAL_TRANSITIONS, frm, to)


def is_forbidden_capability(cap: str) -> bool:
    return cap in FORBIDDEN_CAPABILITIES


def is_forbidden_action(action_type: str) -> bool:
    return action_type in FORBIDDEN_ACTIONS


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


def agent_identity_hash(agent_id: str, name: str, version: str, provider: str,
                        capabilities: list) -> str:
    return _digest({"agent_id": agent_id, "name": name, "version": version,
                    "provider": provider, "capabilities": sorted(capabilities or [])})


def request_hash(agent_id: str, objective: str, input_sources: list) -> str:
    return _digest({"agent_id": agent_id, "objective": objective,
                    "input_sources": sorted(input_sources or [])})


# ── 결정적 ID ──
def agent_event_id(agent_id: str, frm: str, to: str) -> str:
    return "AGE:" + hashlib.sha1(input_digest(agent_id, frm, to).encode()).hexdigest()[:12]


def capability_id(agent_id: str, capability: str) -> str:
    return "ACP:" + hashlib.sha1(input_digest(agent_id, capability).encode()).hexdigest()[:12]


def request_id(agent_id: str, objective: str) -> str:
    return "ARQ:" + hashlib.sha1(input_digest(agent_id, objective).encode()).hexdigest()[:12]


def request_event_id(rid: str, frm: str, to: str) -> str:
    return "RQE:" + hashlib.sha1(input_digest(rid, frm, to).encode()).hexdigest()[:12]


def proposal_id(rid: str, hypothesis: str) -> str:
    return "APP:" + hashlib.sha1(input_digest(rid, hypothesis).encode()).hexdigest()[:12]


def proposal_event_id(pid: str, frm: str, to: str) -> str:
    return "PPE:" + hashlib.sha1(input_digest(pid, frm, to).encode()).hexdigest()[:12]


def action_id(agent_id: str, action_type: str, target: str, timestamp: str) -> str:
    return "ACT:" + hashlib.sha1(
        input_digest(agent_id, action_type, target, timestamp).encode()).hexdigest()[:12]


def review_id(pid: str, reviewer: str, decision: str) -> str:
    return "ARV:" + hashlib.sha1(
        input_digest(pid, reviewer, decision).encode()).hexdigest()[:12]


def budget_key(agent_id: str, period: str) -> str:
    return f"{agent_id}@{period}"


def budget_limit_id(agent_id: str, period: str) -> str:
    return "ABG:" + hashlib.sha1(input_digest(agent_id, period).encode()).hexdigest()[:12]


def budget_usage_id(bkey: str, kind: str, seq: int) -> str:
    return "ABE:" + hashlib.sha1(input_digest(bkey, kind, seq).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "ARA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def detect_cycle(edges: list) -> list:
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
class AgentEvent:
    """에이전트 등록·상태 전이 이벤트(이벤트 소싱). identity 불변."""
    event_id: str
    agent_id: str
    name: str
    version: str
    provider: str
    capabilities: list
    identity_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Capability:
    capability_id: str
    agent_id: str
    capability: str
    allowed: bool                   # 메타데이터 — 실제 권한 아님
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRequestEvent:
    event_id: str
    request_id: str
    agent_id: str
    objective: str
    input_sources: list
    request_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProposalEvent:
    event_id: str
    proposal_id: str
    request_id: str
    hypothesis: str
    methodology: str
    expected_output: str
    risk_notes: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    actor: str = "system"
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentAction:
    action_id: str
    agent_id: str
    action_type: str
    target: str
    result: str
    is_forbidden: bool
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HumanReview:
    review_id: str
    proposal_id: str
    reviewer: str                   # 사람 식별자(필수 — 자동 승인 금지)
    decision: str                   # APPROVE | REJECT | REQUEST_CHANGE
    reason: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BudgetRecord:
    event_id: str
    budget_key: str
    agent_id: str
    period: str
    record_type: str                # LIMIT | USAGE
    max_experiments: int
    max_queries: int
    kind: str                       # USAGE 시 experiment|query
    amount: int
    status: str                     # OK | BLOCKED
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    agent_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentGovernanceReport:
    timestamp: str
    agent_count: int
    agent_state_distribution: dict
    provider_distribution: dict
    request_count: int
    request_state_distribution: dict
    proposal_count: int
    proposal_state_distribution: dict
    action_count: int
    blocked_action_count: int
    review_count: int
    review_decision_distribution: dict
    budget_count: int
    blocked_budget_count: int
    pending_reviews: int

    def to_dict(self) -> dict:
        return asdict(self)
