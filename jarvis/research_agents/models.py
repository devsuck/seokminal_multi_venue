"""Research Agent Framework 자료형 (P11.1) — 연구를 보조하는 AI 에이전트. **연구 보조 전용.**

Data Analyst·Strategy Research·Backtest Analyst·Risk Analyst·Reviewer 에이전트가 Research OS 를 **READ ONLY**
로 참조(파일 기반, import 없음)해 읽기·분석·리포트만 수행한다. **에이전트는 연구 보조원일 뿐 — TRADE·EXECUTE·
DEPLOY·ALLOCATE 금지.** 허용: READ·ANALYZE·REPORT. ASSIST ≠ EXECUTE · ANALYZE ≠ TRADE · REPORT ≠ DEPLOY.
모든 에이전트 활동은 append-only 감사 원장에 남는다. 불변·해시체인·결정적. 물리 원장은 ragt_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 에이전트 유형(5) ──
AGENT_DATA_ANALYST = "DATA_ANALYST"
AGENT_STRATEGY = "STRATEGY_RESEARCH"
AGENT_BACKTEST = "BACKTEST_ANALYST"
AGENT_RISK = "RISK_ANALYST"
AGENT_REVIEWER = "REVIEWER"
AGENT_TYPES = (AGENT_DATA_ANALYST, AGENT_STRATEGY, AGENT_BACKTEST, AGENT_RISK, AGENT_REVIEWER)

# ── 허용 역량(에이전트 권한) ──
CAP_READ = "READ"
CAP_ANALYZE = "ANALYZE"
CAP_REPORT = "REPORT"
ALLOWED_CAPABILITIES = (CAP_READ, CAP_ANALYZE, CAP_REPORT)

# ── 금지 행위(절대 불가) ──
ACT_TRADE = "TRADE"
ACT_EXECUTE = "EXECUTE"
ACT_DEPLOY = "DEPLOY"
ACT_ALLOCATE = "ALLOCATE"
FORBIDDEN_ACTIONS = (ACT_TRADE, ACT_EXECUTE, ACT_DEPLOY, ACT_ALLOCATE)
# 금지 행위 확장 집합(동의어 포함, 탐지용).
FORBIDDEN_ACTION_SET = frozenset({
    ACT_TRADE, ACT_EXECUTE, ACT_DEPLOY, ACT_ALLOCATE,
    "ORDER", "PLACE_ORDER", "SUBMIT_ORDER", "MODIFY", "LIQUIDATE", "REBALANCE",
    "ACTIVATE", "APPROVE", "PROMOTE",
})

# ── 에이전트 생애주기 상태 ──
AGENT_REGISTERED = "REGISTERED"
AGENT_ACTIVE = "ACTIVE"
AGENT_IDLE = "IDLE"
AGENT_RETIRED = "RETIRED"
AGENT_STATES = (AGENT_REGISTERED, AGENT_ACTIVE, AGENT_IDLE, AGENT_RETIRED)

ALLOWED_AGENT_TRANSITIONS = {
    AGENT_REGISTERED: {AGENT_ACTIVE},
    AGENT_ACTIVE: {AGENT_IDLE, AGENT_RETIRED},
    AGENT_IDLE: {AGENT_ACTIVE, AGENT_RETIRED},
    AGENT_RETIRED: set(),
}

# ── 태스크 생애주기 상태 ──
TASK_CREATED = "CREATED"
TASK_ASSIGNED = "ASSIGNED"
TASK_IN_PROGRESS = "IN_PROGRESS"
TASK_COMPLETED = "COMPLETED"
TASK_FAILED = "FAILED"
TASK_CANCELLED = "CANCELLED"
TASK_STATES = (TASK_CREATED, TASK_ASSIGNED, TASK_IN_PROGRESS, TASK_COMPLETED, TASK_FAILED,
               TASK_CANCELLED)

ALLOWED_TASK_TRANSITIONS = {
    TASK_CREATED: {TASK_ASSIGNED, TASK_CANCELLED},
    TASK_ASSIGNED: {TASK_IN_PROGRESS, TASK_CANCELLED},
    TASK_IN_PROGRESS: {TASK_COMPLETED, TASK_FAILED},
    TASK_COMPLETED: set(),
    TASK_FAILED: set(),
    TASK_CANCELLED: set(),
}

# ── 활동(감사) 종류 ──
ACT_KIND_REGISTERED = "AGENT_REGISTERED"
ACT_KIND_PROFILE = "PROFILE_CREATED"
ACT_KIND_AGENT_TRANSITION = "AGENT_TRANSITION"
ACT_KIND_TASK_EVENT = "TASK_EVENT"
ACT_KIND_MESSAGE = "MESSAGE_SENT"
ACT_KIND_REPORT = "REPORT_SUBMITTED"
ACT_KIND_BLOCKED = "ACTION_BLOCKED"
ACTIVITY_KINDS = (ACT_KIND_REGISTERED, ACT_KIND_PROFILE, ACT_KIND_AGENT_TRANSITION,
                  ACT_KIND_TASK_EVENT, ACT_KIND_MESSAGE, ACT_KIND_REPORT, ACT_KIND_BLOCKED)


class ImmutableAgentError(Exception):
    """불변 에이전트 등록 위반."""


class ImmutableProfileError(Exception):
    """불변 에이전트 프로파일 위반."""


class ImmutableMessageError(Exception):
    """불변 메시지 위반."""


class ImmutableReportError(Exception):
    """불변 에이전트 리포트 위반."""


class InvalidAgentType(Exception):
    """미등록 에이전트 유형."""


class InvalidCapability(Exception):
    """미등록/미허용 역량."""


class ForbiddenAgentAction(Exception):
    """금지 행위(TRADE·EXECUTE·DEPLOY·ALLOCATE) 시도 — 차단."""


class CapabilityDenied(Exception):
    """에이전트 프로파일에 없는 역량 요청."""


class UnknownAgentError(Exception):
    """미등록 에이전트 참조."""


class IllegalTaskTransition(Exception):
    """허용되지 않은 태스크 상태 전이."""


class IllegalAgentTransition(Exception):
    """허용되지 않은 에이전트 상태 전이."""


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
def agent_id(name: str) -> str:
    return "RGA:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def profile_id(agent: str) -> str:
    return "RGP:" + hashlib.sha1(input_digest(agent).encode()).hexdigest()[:12]


def task_id(agent: str, action: str, target: str, description: str) -> str:
    return "RGT:" + hashlib.sha1(
        input_digest(agent, action, target, description).encode()).hexdigest()[:12]


def task_event_id(task: str, to_state: str) -> str:
    return "RTE:" + hashlib.sha1(input_digest(task, to_state).encode()).hexdigest()[:12]


def message_id(from_agent: str, to_agent: str, subject: str, content: str) -> str:
    return "RGM:" + hashlib.sha1(
        input_digest(from_agent, to_agent, subject, content).encode()).hexdigest()[:12]


def report_id(agent: str, task: str, scope: str) -> str:
    return "RGR:" + hashlib.sha1(
        input_digest(agent, task, scope).encode()).hexdigest()[:12]


def activity_id(kind: str, reference: str, occurred_at: str) -> str:
    return "RGL:" + hashlib.sha1(
        input_digest(kind, reference, occurred_at).encode()).hexdigest()[:12]


# ── 결정적 권한 유틸 ──
def is_forbidden_action(action: str) -> bool:
    """금지 행위(TRADE·EXECUTE·DEPLOY·ALLOCATE 및 동의어) 여부(결정적). **차단 판단.**"""
    return (action or "").strip().upper() in FORBIDDEN_ACTION_SET


def is_allowed_capability(action: str) -> bool:
    return (action or "").strip().upper() in ALLOWED_CAPABILITIES


def can_transition_task(frm: str, to: str) -> bool:
    return to in ALLOWED_TASK_TRANSITIONS.get(frm, set())


def can_transition_agent(frm: str, to: str) -> bool:
    return to in ALLOWED_AGENT_TRANSITIONS.get(frm, set())


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    name: str
    agent_type: str
    description: str
    registered_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentProfileRecord:
    profile_id: str
    agent: str
    agent_type: str
    capabilities: list
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TaskEventRecord:
    task_event_id: str
    task_id: str
    agent: str
    action: str
    target: str
    description: str
    from_state: str
    to_state: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MessageRecord:
    message_id: str
    from_agent: str
    to_agent: str
    subject: str
    content: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentReportRecord:
    report_id: str
    agent: str
    task_id: str
    scope: str
    findings: list
    summary: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ActivityRecord:
    activity_id: str
    kind: str
    agent: str
    action: str
    reference: str
    detail: str
    allowed: bool
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentSummary:
    timestamp: str
    agent_count: int
    profile_count: int
    task_event_count: int
    message_count: int
    report_count: int
    activity_count: int
    blocked_count: int

    def to_dict(self) -> dict:
        return asdict(self)
