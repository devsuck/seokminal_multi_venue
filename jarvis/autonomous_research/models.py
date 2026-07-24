"""Autonomous Research Loop & Continuous Improvement 자료형 (P25) — 연구 지능 전용. **동작 없음.**

이전 연구 결과를 분석, 개선 기회를 식별, 연구 제안을 생성, 실험 계획을 작성, 개선 사이클을 추적, 실패·성공에서
학습한다. **이것은 지식을 만든다 — 거래 행위를 만들지 않는다.** 실험 자동 실행·전략 배포·모델 승인·거래·자본 배분·
프로덕션 수정을 하지 않는다. LOOP CREATES KNOWLEDGE ≠ TRADING ACTIONS · PROPOSAL ≠ APPROVAL · PLAN ≠ EXECUTION.
불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 ar_ 접두사. 상위 계층(P10~P24)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 연구 사이클 생애주기(6) — 이벤트 소싱 ──
C_CREATED = "CREATED"
C_ANALYZING = "ANALYZING"
C_PLANNED = "PLANNED"
C_EVALUATING = "EVALUATING"
C_COMPLETED = "COMPLETED"
C_ARCHIVED = "ARCHIVED"
CYCLE_STATES = (C_CREATED, C_ANALYZING, C_PLANNED, C_EVALUATING, C_COMPLETED, C_ARCHIVED)
CYCLE_TRANSITIONS = {
    C_CREATED: {C_ANALYZING},
    C_ANALYZING: {C_ANALYZING, C_PLANNED},
    C_PLANNED: {C_PLANNED, C_EVALUATING},
    C_EVALUATING: {C_EVALUATING, C_COMPLETED, C_PLANNED},
    C_COMPLETED: {C_ARCHIVED, C_ANALYZING},
    C_ARCHIVED: set(),
}

# ── 연구 제안 상태(5) — 이벤트 소싱, 사람 검토 필수 ──
P_DRAFT = "DRAFT"
P_SUBMITTED = "SUBMITTED"
P_REVIEWED = "REVIEWED"
P_ACCEPTED = "ACCEPTED"
P_REJECTED = "REJECTED"
PROPOSAL_STATES = (P_DRAFT, P_SUBMITTED, P_REVIEWED, P_ACCEPTED, P_REJECTED)
PROPOSAL_TRANSITIONS = {
    P_DRAFT: {P_SUBMITTED},
    P_SUBMITTED: {P_REVIEWED, P_DRAFT},
    P_REVIEWED: {P_ACCEPTED, P_REJECTED, P_SUBMITTED},
    P_ACCEPTED: set(),
    P_REJECTED: set(),
}

# ── 기회 탐지 패턴 ──
OPPORTUNITY_PATTERNS = ("REPEATED_FAILURES", "VALIDATION_WARNINGS", "ROBUSTNESS_ISSUES",
                        "MISSING_EXPERIMENTS", "DUPLICATED_RESEARCH")
# ── 학습 종류 ──
LEARNING_KINDS = ("SUCCESSFUL_PATTERN", "FAILED_PATTERN", "RESEARCH_LESSON")
# ── 우선순위 등급 ──
PRIORITY_LEVELS = ("LOW", "MEDIUM", "HIGH")
# ── 위험 등급 ──
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")

# ── 아티팩트 유형 ──
ART_CYCLE = "CYCLE"
ART_OPPORTUNITY = "OPPORTUNITY"
ART_PROPOSAL = "PROPOSAL"
ART_PLAN = "EXPERIMENT_PLAN"
ART_FEEDBACK = "FEEDBACK"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "MODIFY_MODEL", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE_LIVE",
    "SELECT_STRATEGY", "PROMOTE", "AUTONOMOUS_APPROVAL", "AUTONOMOUS_DEPLOYMENT",
})


class ImmutableCycleError(Exception):
    """불변 사이클(중복 genesis) 위반."""


class IllegalCycleTransition(Exception):
    """유효하지 않은 사이클 전이 — 차단."""


class IllegalProposalTransition(Exception):
    """유효하지 않은 제안 전이 — 차단."""


class ReviewerRequired(Exception):
    """제안 ACCEPTED/REJECTED 는 사람 검토(reviewer) 필수 — 자동 승인 금지."""


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


# ── 결정적 ID (AR* 스킴) ──
def cycle_id(objective) -> str:
    return _id("ARC", objective)


def cycle_event_id(cyc, to, seq) -> str:
    return _id("ARY", cyc, to, seq)


def opportunity_id(source_pattern, description) -> str:
    return _id("ARO", source_pattern, description)


def proposal_id(cyc, hypothesis) -> str:
    return _id("ARP", cyc, hypothesis)


def proposal_event_id(prop, to, seq) -> str:
    return _id("ARM", prop, to, seq)


def experiment_plan_id(prop, seq) -> str:
    return _id("ARX", prop, seq)


def feedback_id(cyc, seq) -> str:
    return _id("ARF", cyc, seq)


def learning_event_id(cyc, kind, seq) -> str:
    return _id("ARL", cyc, kind, seq)


def report_id(scope, created_at) -> str:
    return _id("ARR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("ARA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_cycle_transition(frm, to) -> bool:
    return to in CYCLE_TRANSITIONS.get(frm, set())


def can_proposal_transition(frm, to) -> bool:
    return to in PROPOSAL_TRANSITIONS.get(frm, set())


def priority_score(evidence_count, severity_weight=1.0) -> float:
    """기회 우선순위 점수(0..1, 결정적). **점수만 — 자동 선택 없음.**"""
    try:
        n = max(0, int(evidence_count))
        w = float(severity_weight)
    except (TypeError, ValueError):
        return 0.0
    raw = 1.0 - 1.0 / (1.0 + n * max(0.0, w))
    return round(min(1.0, max(0.0, raw)), 6)


def classify_priority(score) -> str:
    """우선순위 점수 → 등급(결정적, 관찰용)."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "LOW"
    if s >= 0.7:
        return "HIGH"
    if s >= 0.4:
        return "MEDIUM"
    return "LOW"


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
class CycleEventRecord:
    cycle_event_id: str
    cycle_id: str
    objective: str
    source_references: list
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
class OpportunityRecord:
    opportunity_id: str
    cycle_id: str
    source_pattern: str
    description: str
    evidence: dict
    priority_score: float
    priority_level: str
    is_auto_selected: bool  # 항상 False — 점수만, 자동 선택 없음
    detected_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProposalEventRecord:
    proposal_event_id: str
    proposal_id: str
    cycle_id: str
    opportunity_id: str
    hypothesis: str
    expected_value: str
    risk: str
    required_validation: list
    from_state: str
    to_state: str
    reviewer: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentPlanRecord:
    plan_id: str
    proposal_id: str
    datasets: list
    features: list
    validation_requirements: list
    success_metrics: list
    is_executable: bool  # 항상 False — 계획만, 실행 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearningFeedbackRecord:
    feedback_id: str
    cycle_id: str
    result_summary: str
    lessons: list
    future_direction: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearningEventRecord:
    learning_event_id: str
    cycle_id: str
    kind: str
    pattern: str
    evidence: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionReportRecord:
    report_id: str
    scope: str
    cycle_count: int
    active_cycle_count: int
    completed_cycle_count: int
    opportunity_count: int
    proposal_count: int
    accepted_proposal_count: int
    experiment_plan_count: int
    feedback_count: int
    learning_event_count: int
    pattern_distribution: dict
    learning_distribution: dict
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
class ResearchLoopSummary:
    timestamp: str
    cycle_event_count: int
    cycle_count: int
    opportunity_count: int
    proposal_event_count: int
    proposal_count: int
    experiment_plan_count: int
    feedback_count: int
    learning_event_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
