"""Research Workflow 자료형 (P64-67) — 오케스트레이션/세션/결정메모/설명가능성. **조율만, 실행 없음.**

기존 서브시스템(research_queue·research_assistant·research_council·portfolio_research·
research_risk_intelligence·research_ingestion)을 **조율**하는 계층의 공통 자료형·해시·ID.
새 지능/새 실험 저장소를 만들지 않는다 — 워크플로/세션 이벤트만 자체 원장(rwf_)에 append.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── P64 워크플로 단계(문서 파이프라인) ──
S_REQUEST = "REQUEST"
S_QUEUE = "QUEUE"
S_RECALL = "RECALL"
S_COUNCIL = "COUNCIL"
S_DESIGN = "DESIGN"
S_BACKTEST = "BACKTEST"
S_VALIDATION = "VALIDATION"
S_PORTFOLIO = "PORTFOLIO"
S_RISK = "RISK"
S_PAPER = "PAPER"
S_DECISION = "DECISION"
S_HUMAN = "HUMAN_DECISION"
STAGES = (S_REQUEST, S_QUEUE, S_RECALL, S_COUNCIL, S_DESIGN, S_BACKTEST, S_VALIDATION,
          S_PORTFOLIO, S_RISK, S_PAPER, S_DECISION, S_HUMAN)

# 단계 상태
ST_PENDING = "PENDING"
ST_COMPLETED = "COMPLETED"
ST_BLOCKED = "BLOCKED"        # 외부 입력 대기(부분 완료) — 조작하지 않음
ST_FAILED = "FAILED"
ST_SKIPPED = "SKIPPED"
ST_CANCELLED = "CANCELLED"

# 외부 입력이 필요한 단계(오케스트레이터는 이를 실행하지 않는다 — 결과만 소비)
EXTERNAL_STAGES = frozenset({S_DESIGN, S_BACKTEST, S_PAPER})

# ── P66 세션 상태 ──
SESS_ACTIVE = "ACTIVE"
SESS_PAUSED = "PAUSED"
SESS_ARCHIVED = "ARCHIVED"

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
})


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items() if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def content_digest(payload) -> str:
    return _digest(payload)


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def workflow_id(request, seed="") -> str:
    return _id("RWF", request, seed)


def stage_event_id(run_id, stage, seq) -> str:
    return _id("RWFE", run_id, stage, seq)


def session_id(goal, seed="") -> str:
    return _id("RSES", goal, seed)


def session_event_id(sess_id, kind, seq) -> str:
    return _id("RSESE", sess_id, kind, seq)


@dataclass(frozen=True)
class StageEvent:
    event_id: str
    run_id: str
    request: str
    stage: str
    status: str
    from_stage: str
    output_digest: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowState:
    run_id: str
    request: str
    current_stage: str
    completed_stages: list
    blocked_stage: str
    cancelled: bool
    stage_outputs: dict            # stage -> summary dict (in-memory, read-only synthesis)
    execution_log: list            # deterministic per-stage log
    requires_human_decision: bool
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DecisionMemo:
    question: str
    recommendation: str
    rationale: str
    evidence: dict
    supporting_arguments: list
    counter_arguments: list
    historical_similar_cases: list
    portfolio_impact: dict
    risk_summary: dict
    confidence: str
    confidence_breakdown: dict
    remaining_unknowns: list
    suggested_next_research: list
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionEvent:
    event_id: str
    session_id: str
    kind: str                      # CREATE | RESUME | PAUSE | ARCHIVE | PROGRESS
    to_state: str
    payload_digest: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionState:
    session_id: str
    goal: str
    state: str
    goals: list
    progress: list
    pending_work: list
    completed_experiments: list
    lessons_learned: list
    open_questions: list
    updated_at: str
    is_advisory: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceChain:
    topic: str
    chain: list                    # ordered nodes Experiment→…→Recommendation
    edges: list
    confidence: str
    confidence_breakdown: dict
    why_this_conclusion: str
    why_it_may_be_wrong: list
    alternative_interpretations: list
    missing_evidence: list
    references_experiments: list   # 실제 실험/기록 참조(설명가능성)
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
