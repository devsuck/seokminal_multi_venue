"""Agent Runtime Layer 자료형 (P45) — 연구 에이전트 런타임. **거래·배포·실행·자본 결정 없음.**

연구 에이전트의 생애주기·태스크 배정·산출물·메모리 참조·상태·로그를 관리한다. **에이전트는 거래·배포·자본 결정을 할 수
없다. 무제한 도구 접근 없음(제한된 연구 능력 허용목록만).** execution/broker/live_trading/portfolio_execution import·
호출 없음. AGENT RUNTIME ≠ AUTONOMOUS TRADING · 산출물은 사람 검토용. 불변·append-only·SHA256 해시체인·이벤트 소싱·
결정적. 물리 원장 agrt_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 에이전트 생애주기(5) — 이벤트 소싱 ──
A_CREATED = "CREATED"
A_READY = "READY"
A_WORKING = "WORKING"
A_WAITING_REVIEW = "WAITING_REVIEW"
A_ARCHIVED = "ARCHIVED"
AGENT_STATES = (A_CREATED, A_READY, A_WORKING, A_WAITING_REVIEW, A_ARCHIVED)
AGENT_TRANSITIONS = {
    A_CREATED: {A_READY},
    A_READY: {A_WORKING, A_ARCHIVED},
    A_WORKING: {A_WAITING_REVIEW},
    A_WAITING_REVIEW: {A_READY, A_ARCHIVED},
    A_ARCHIVED: set(),
}

# ── 에이전트 역할 ──
AGENT_ROLES = ("ANALYST", "RESEARCHER", "REVIEWER", "SUMMARIZER", "PLANNER", "MONITOR")

# ── 허용 능력(연구 전용) — 무제한 도구 접근 금지. 이 집합 밖은 거부. ──
ALLOWED_CAPABILITIES = ("ANALYZE", "SIMULATE", "RECORD", "REPORT", "RECOMMEND",
                        "QUERY_MEMORY", "READ_DATA")

# ── 산출물 종류 ──
OUTPUT_KINDS = ("ANALYSIS", "SIMULATION", "SUMMARY", "RECOMMENDATION", "METRIC", "NOTE")

# ── 로그 레벨 ──
LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

# ── 메모리 참조 대상(READ ONLY) ──
MEMORY_LAYERS = ("research_memory_intelligence", "research_memory_system",
                 "experiment_tracking", "model_management", "data_infrastructure")

# ── 아티팩트 유형(계보) ──
ART_AGENT = "AGENT"
ART_TASK = "TASK"
ART_REPORT = "REPORT"

# ── 절대 금지(거래·실행·배포·배분) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "AUTO_EXECUTE",
    "AUTO_TRADE", "SELF_EXECUTE", "AUTO_DEPLOY", "SERVE_LIVE",
})
# ── 금지 능력(무제한 접근/자본 결정) — 능력 허용목록과 별개로 명시 거부. ──
FORBIDDEN_CAPABILITIES = frozenset({
    "*", "ALL", "ANY", "ADMIN", "ROOT", "SHELL", "TRADE", "EXECUTE", "DEPLOY", "ALLOCATE",
    "ALLOCATE_CAPITAL", "PLACE_ORDER", "BROKER", "WITHDRAW", "TRANSFER", "UNRESTRICTED",
})


class ImmutableAgentError(Exception):
    """불변 에이전트(중복 genesis) 위반."""


class IllegalAgentTransition(Exception):
    """유효하지 않은 에이전트 전이 — 차단."""


class ForbiddenCapabilityError(Exception):
    """금지·미허용 능력 요청 — 차단(무제한 도구 접근 금지)."""


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


def output_content_hash(payload) -> str:
    return _digest({"payload": payload})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (ARN* 스킴) ──
def agent_id(name) -> str:
    return _id("ARNA", name)


def agent_event_id(agent, to, seq) -> str:
    return _id("ARNE", agent, to, seq)


def task_id(agent, title, seq) -> str:
    return _id("ARNT", agent, title, seq)


def output_id(agent, task, seq) -> str:
    return _id("ARNO", agent, task, seq)


def memref_id(agent, layer, ref) -> str:
    return _id("ARNM", agent, layer, ref)


def log_id(agent, seq) -> str:
    return _id("ARNL", agent, seq)


def report_id(scope, created_at) -> str:
    return _id("ARNR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("ARNF", atype, ref)


# ── 결정적 분석/검증 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def is_forbidden_capability(cap) -> bool:
    return (cap or "").strip().upper() in FORBIDDEN_CAPABILITIES


def is_allowed_capability(cap) -> bool:
    c = (cap or "").strip().upper()
    return c in ALLOWED_CAPABILITIES and c not in FORBIDDEN_CAPABILITIES


def validate_capabilities(caps):
    """능력 허용목록 검증. 금지/미허용/무제한 능력이 있으면 ForbiddenCapabilityError."""
    norm = []
    for c in (caps or []):
        cc = (c or "").strip().upper()
        if not cc:
            continue
        if is_forbidden_capability(cc):
            raise ForbiddenCapabilityError(f"금지 능력 {cc}")
        if cc not in ALLOWED_CAPABILITIES:
            raise ForbiddenCapabilityError(f"미허용 능력 {cc} — 허용목록 밖(무제한 접근 금지)")
        norm.append(cc)
    return sorted(set(norm))


def can_agent_transition(frm, to) -> bool:
    return to in AGENT_TRANSITIONS.get(frm, set())


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


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class AgentEventRecord:
    agent_event_id: str
    agent_id: str
    name: str
    role: str
    capabilities: list
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
class TaskAssignmentRecord:
    task_id: str
    agent_id: str
    title: str
    description: str
    status: str
    is_binding: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OutputRecord:
    output_id: str
    agent_id: str
    task_id: str
    kind: str
    content_hash: str
    summary: str
    is_binding: bool
    is_executed: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryReferenceRecord:
    memref_id: str
    agent_id: str
    memory_layer: str
    memory_ref: str
    purpose: str
    is_read_only: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LogRecord:
    log_id: str
    agent_id: str
    level: str
    message: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentReportRecord:
    report_id: str
    scope: str
    agent_count: int
    working_agent_count: int
    waiting_review_count: int
    assignment_count: int
    output_count: int
    memref_count: int
    log_count: int
    role_distribution: dict
    state_distribution: dict
    requires_human_review: bool
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
class AgentSummary:
    timestamp: str
    agent_event_count: int
    agent_count: int
    assignment_count: int
    output_count: int
    memref_count: int
    log_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
