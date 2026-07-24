"""Autonomous Experiment Manager 자료형 (P11.4) — AI 보조 실험 생성. **제안 전용.**

실험 제안(계획·연구요청·결과 수집)을 생성한다. **라이브 전략 실행은 허용되지 않는다.** 생애주기: PROPOSED→
REVIEWED→APPROVED_FOR_RESEARCH→COMPLETED. **APPROVED_FOR_RESEARCH 는 거래 승인이 아니다.** 실행·배포 없음.
PROPOSAL ≠ EXECUTION · APPROVED_FOR_RESEARCH ≠ TRADING_APPROVAL · RESULT ≠ DEPLOYMENT. 불변·append-only·해시체인.
물리 원장은 exm_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── 실험 생애주기 상태 ──
EXP_PROPOSED = "PROPOSED"
EXP_REVIEWED = "REVIEWED"
EXP_APPROVED_FOR_RESEARCH = "APPROVED_FOR_RESEARCH"
EXP_COMPLETED = "COMPLETED"
EXPERIMENT_STATES = (EXP_PROPOSED, EXP_REVIEWED, EXP_APPROVED_FOR_RESEARCH, EXP_COMPLETED)

ALLOWED_TRANSITIONS = {
    EXP_PROPOSED: {EXP_REVIEWED},
    EXP_REVIEWED: {EXP_APPROVED_FOR_RESEARCH},
    EXP_APPROVED_FOR_RESEARCH: {EXP_COMPLETED},
    EXP_COMPLETED: set(),
}

# 연구 요청/결과 수집이 가능한 상태(연구 승인 이후).
RESEARCH_STATES = frozenset({EXP_APPROVED_FOR_RESEARCH, EXP_COMPLETED})
# 계획 생성이 가능한 상태(승인 전 설계 단계).
PLANNABLE_STATES = frozenset({EXP_PROPOSED, EXP_REVIEWED})

# ── 실험 결과 결론 ──
OUTCOME_SUPPORTED = "SUPPORTED"
OUTCOME_REFUTED = "REFUTED"
OUTCOME_INCONCLUSIVE = "INCONCLUSIVE"
OUTCOME_PENDING = "PENDING"
OUTCOMES = (OUTCOME_SUPPORTED, OUTCOME_REFUTED, OUTCOME_INCONCLUSIVE, OUTCOME_PENDING)

# ── 금지(실행·배포·거래 승인) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "RUN_LIVE", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "GO_LIVE", "LAUNCH_LIVE",
    "PLACE_ORDER", "ACTIVATE", "APPROVE_TRADING", "TRADING_APPROVAL",
})


class ImmutableExperimentError(Exception):
    """불변 실험(제안) 위반."""


class ImmutablePlanError(Exception):
    """불변 실험 계획 위반."""


class ImmutableRequestError(Exception):
    """불변 연구 요청 위반."""


class ImmutableResultError(Exception):
    """불변 결과 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class IllegalExperimentTransition(Exception):
    """허용되지 않은 실험 상태 전이."""


class InvalidOutcome(Exception):
    """미등록 결과 결론."""


class UnknownExperimentError(Exception):
    """미등록 실험 참조."""


class ExperimentStateError(Exception):
    """현재 상태에서 허용되지 않은 작업."""


class ForbiddenExecutionError(Exception):
    """실행·배포·거래 시도 — 차단(제안 전용)."""


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
def experiment_id(title: str, proposer: str, hypothesis: str) -> str:
    return "EXM:" + hashlib.sha1(
        input_digest(title, proposer, hypothesis).encode()).hexdigest()[:12]


def event_id(experiment: str, to_state: str) -> str:
    return "EXE:" + hashlib.sha1(input_digest(experiment, to_state).encode()).hexdigest()[:12]


def plan_id(experiment: str, method: str) -> str:
    return "EXL:" + hashlib.sha1(input_digest(experiment, method).encode()).hexdigest()[:12]


def request_id(experiment: str, scope: str) -> str:
    return "EXR:" + hashlib.sha1(input_digest(experiment, scope).encode()).hexdigest()[:12]


def result_id(experiment: str, collected_at: str) -> str:
    return "EXT:" + hashlib.sha1(input_digest(experiment, collected_at).encode()).hexdigest()[:12]


def report_id(experiment: str, scope: str, generated_at: str) -> str:
    return "EXO:" + hashlib.sha1(
        input_digest(experiment, scope, generated_at).encode()).hexdigest()[:12]


# ── 결정적 유틸 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ExperimentEventRecord:
    event_id: str
    experiment_id: str
    title: str
    hypothesis: str
    proposer: str
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
class ExperimentPlanRecord:
    plan_id: str
    experiment_id: str
    method: str
    variables: list
    dataset: str
    success_criteria: list
    horizon: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRequestRecord:
    request_id: str
    experiment_id: str
    plan_id: str
    scope: str
    justification: str
    research_only: bool
    trading_approval: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentResultRecord:
    result_id: str
    experiment_id: str
    metrics: dict
    findings: list
    outcome: str
    summary: str
    collected_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentReportRecord:
    report_id: str
    experiment_id: str
    scope: str
    lifecycle_state: str
    plan_count: int
    request_count: int
    result_count: int
    outcome_distribution: dict
    trading_approval: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentSummary:
    timestamp: str
    experiment_event_count: int
    experiment_count: int
    plan_count: int
    request_count: int
    result_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
