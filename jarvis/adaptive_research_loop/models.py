"""Adaptive Research Loop 자료형 (P12.4) — 연구 프로세스 개선 피드백 루프. **개선 기록 전용.**

실패 실험 분석·개선 제안·워크플로 적응·연구 효율 추적을 관리한다. **개선을 기록만 하며 자동 수정을 하지 않는다.**
개선 제안은 모델·전략·권한을 수정할 수 없고 인간 리뷰 기록이 필요하다. IMPROVEMENT ≠ EXECUTION · PROPOSAL ≠
MODIFICATION · RECORDED ≠ DEPLOYMENT. 불변·append-only·이벤트 소싱·SHA256 해시체인·결정적. 물리 원장은 arl_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 개선 제안 생애주기(6) ──
L_OBSERVED = "OBSERVED"
L_ANALYZED = "ANALYZED"
L_PROPOSED = "PROPOSED"
L_REVIEWED = "REVIEWED"
L_RECORDED = "RECORDED"
L_ARCHIVED = "ARCHIVED"
LOOP_STATES = (L_OBSERVED, L_ANALYZED, L_PROPOSED, L_REVIEWED, L_RECORDED, L_ARCHIVED)

ALLOWED_TRANSITIONS = {
    L_OBSERVED: {L_ANALYZED},
    L_ANALYZED: {L_PROPOSED},
    L_PROPOSED: {L_REVIEWED, L_ANALYZED},
    L_REVIEWED: {L_RECORDED, L_ANALYZED},
    L_RECORDED: {L_ARCHIVED},
    L_ARCHIVED: set(),
}

# ── 적응 카테고리(6) ──
ADAPTATION_CATEGORIES = ("WORKFLOW", "DATA_QUALITY", "EXPERIMENT_DESIGN", "VALIDATION",
                         "EFFICIENCY", "COLLABORATION")

# ── 리뷰 결정 ──
DEC_ACCEPT = "ACCEPT"
DEC_REWORK = "REWORK"
DEC_NOTE = "NOTE"
DECISIONS = (DEC_ACCEPT, DEC_REWORK, DEC_NOTE)

# ── 효율 비교 방향 ──
DIR_IMPROVED = "IMPROVED"
DIR_REGRESSED = "REGRESSED"
DIR_UNCHANGED = "UNCHANGED"

# ── 금지(자동 수정·배포) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "AUTO_UPDATE", "AUTO_DEPLOY", "AUTO_PROMOTE", "MODIFY_SYSTEM", "MODIFY_MODEL", "MODIFY_STRATEGY",
    "MODIFY_PERMISSION", "DEPLOY", "EXECUTE", "PROMOTE_LIVE", "APPROVE_LIVE",
})


class ImmutableCycleError(Exception):
    """불변 루프 사이클 위반."""


class ImmutableFeedbackError(Exception):
    """불변 피드백 위반."""


class ImmutableProposalError(Exception):
    """불변 개선 제안(중복) 위반."""


class ImmutableMetricError(Exception):
    """불변 효율 메트릭 위반."""


class IllegalLoopTransition(Exception):
    """유효하지 않은 개선 제안 상태 전이 — 거부."""


class InvalidCategory(Exception):
    """미등록 적응 카테고리."""


class InvalidDecision(Exception):
    """미등록 리뷰 결정."""


class MissingReviewError(Exception):
    """인간 리뷰 기록 누락 — 거부."""


class ForbiddenModificationError(Exception):
    """모델/전략/권한/시스템 수정 시도 — 거부."""


class UnknownCycleError(Exception):
    """미등록 루프 사이클 참조."""


class UnknownProposalError(Exception):
    """미등록 개선 제안 참조."""


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


# ── 결정적 ID (AL* 스킴) ──
def cycle_id(name: str) -> str:
    return "ALC:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def feedback_id(cycle: str, source_ref: str, observation: str) -> str:
    return "ALF:" + hashlib.sha1(
        input_digest(cycle, source_ref, observation).encode()).hexdigest()[:12]


def proposal_id(cycle: str, title: str) -> str:
    return "ALP:" + hashlib.sha1(input_digest(cycle, title).encode()).hexdigest()[:12]


def proposal_event_id(proposal: str, to_state: str, seq: int) -> str:
    return "ALV:" + hashlib.sha1(input_digest(proposal, to_state, seq).encode()).hexdigest()[:12]


def metric_id(cycle_a: str, cycle_b: str, metric: str) -> str:
    return "ALM:" + hashlib.sha1(input_digest(cycle_a, cycle_b, metric).encode()).hexdigest()[:12]


def adaptation_id(proposal: str, seq: int) -> str:
    return "ALA:" + hashlib.sha1(input_digest(proposal, seq).encode()).hexdigest()[:12]


def report_id(cycle: str, scope: str, generated_at: str) -> str:
    return "ALR:" + hashlib.sha1(
        input_digest(cycle, scope, generated_at).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def compare_direction(value_a: float, value_b: float, higher_is_better: bool = True) -> tuple:
    """효율 비교 방향·델타(결정적). 반환 (direction, delta)."""
    delta = round(float(value_b) - float(value_a), 8)
    if delta == 0:
        return DIR_UNCHANGED, 0.0
    improved = (delta > 0) if higher_is_better else (delta < 0)
    return (DIR_IMPROVED if improved else DIR_REGRESSED), delta


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class LoopCycleRecord:
    cycle_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    cycle_id: str
    source_layer: str
    source_ref: str
    observation: str
    category: str
    created_at: str
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
    feedback_ref: str
    category: str
    title: str
    description: str
    proposed_change: str
    root_cause: str
    reviewer: str
    decision: str
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
class EfficiencyMetricRecord:
    metric_id: str
    cycle_a: str
    cycle_b: str
    metric_name: str
    value_a: float
    value_b: float
    delta: float
    direction: str
    compared_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AdaptationRecord:
    adaptation_id: str
    proposal_id: str
    cycle_id: str
    outcome: str
    evidence_ref: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LoopReportRecord:
    report_id: str
    cycle_id: str
    scope: str
    feedback_count: int
    proposal_count: int
    reviewed_count: int
    recorded_count: int
    metric_count: int
    category_distribution: dict
    is_binding: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LoopSummary:
    timestamp: str
    cycle_count: int
    feedback_count: int
    proposal_event_count: int
    metric_count: int
    adaptation_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
