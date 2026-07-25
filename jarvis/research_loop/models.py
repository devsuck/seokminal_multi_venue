"""Research Loop 자료형 (C5) — 헌장 연구 워크플로 모델. **사람 승인 필수, 자동 실행/집행 없음.**

헌장 워크플로: 관측→가설→제안→**사람 승인**→(연구)실행→검증→리포트→지식→메모리. 각 단계는 **기록된 상태**일 뿐
루프는 아무것도 자동 실행하지 않는다. 제안→실행 전이는 **사람 승인 없이는 절대 통과 불가**(게이트). 엔진은
approve()/execute()/trade()/deploy()/allocate() 를 노출하지 않는다 — 사람의 결정을 '기록'할 뿐이다.
'실행(EXECUTION)' 은 연구 실행(실험 수행) 단계이며 거래 집행이 아니다. 불변·append-only·SHA256 해시체인·이벤트 소싱.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 연구 루프 단계 — 이벤트 소싱 ──
S_OBSERVATION = "OBSERVATION"
S_HYPOTHESIS = "HYPOTHESIS"
S_PROPOSAL = "PROPOSAL"
S_EXECUTION = "EXECUTION"        # 연구 실행(실험 수행) — 거래 집행 아님
S_VALIDATION = "VALIDATION"
S_REPORT = "REPORT"
S_KNOWLEDGE = "KNOWLEDGE"
S_MEMORY = "MEMORY"
S_ARCHIVED = "ARCHIVED"
S_REJECTED = "REJECTED"
STAGES = (S_OBSERVATION, S_HYPOTHESIS, S_PROPOSAL, S_EXECUTION, S_VALIDATION, S_REPORT,
          S_KNOWLEDGE, S_MEMORY, S_ARCHIVED, S_REJECTED)

STAGE_TRANSITIONS = {
    S_OBSERVATION: {S_HYPOTHESIS},
    S_HYPOTHESIS: {S_PROPOSAL},
    S_PROPOSAL: {S_EXECUTION, S_REJECTED},   # EXECUTION 은 사람 승인 게이트로 보호
    S_EXECUTION: {S_VALIDATION},
    S_VALIDATION: {S_REPORT},
    S_REPORT: {S_KNOWLEDGE},
    S_KNOWLEDGE: {S_MEMORY},
    S_MEMORY: {S_ARCHIVED},
    S_ARCHIVED: set(),
    S_REJECTED: set(),
}
# 진입 전 사람 승인이 반드시 필요한 단계
APPROVAL_GATED_STAGES = frozenset({S_EXECUTION})

# ── 사람 검토 결정 ──
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"
REVIEW_DECISIONS = (REVIEW_APPROVED, REVIEW_REJECTED)
REVIEW_PENDING = "PENDING_HUMAN_REVIEW"

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
    "AUTO_APPROVE", "AUTO_EXECUTE",
})

DISCLAIMER = ("Research Loop — 헌장 워크플로의 읽기전용 모델. 각 단계는 기록된 상태일 뿐 자동 실행·자동 집행·자동 승인이 "
              "없다. 제안→실행은 사람 승인 없이는 통과 불가(Human approval is always required). "
              "'실행'은 연구 실행이며 거래 집행이 아니다. 사람이 결정한다.")


class ImmutableLoopError(Exception):
    """불변 루프(중복 genesis) 위반."""


class IllegalStageTransition(Exception):
    """유효하지 않은 단계 전이."""


class ApprovalRequiredError(Exception):
    """사람 승인 게이트 — 승인 없이 실행 단계 진입 시도 차단."""


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def loop_id(title) -> str:
    return _id("RLPL", title)


def loop_event_id(loop, to, seq) -> str:
    return _id("RLPE", loop, to, seq)


def review_id(loop, seq) -> str:
    return _id("RLPV", loop, seq)


def report_id(scope, created_at) -> str:
    return _id("RLPR", scope, created_at)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_stage_transition(frm, to) -> bool:
    return to in STAGE_TRANSITIONS.get(frm, set())


def requires_human_approval(to_stage) -> bool:
    return to_stage in APPROVAL_GATED_STAGES


@dataclass(frozen=True)
class LoopStageEvent:
    loop_event_id: str
    loop_id: str
    title: str
    from_stage: str
    to_stage: str
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HumanReviewRecord:
    review_id: str
    loop_id: str
    decision: str            # APPROVED | REJECTED (사람이 내린 결정의 기록)
    reviewer: str            # 사람 식별자(필수)
    is_human: bool
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LoopReportRecord:
    report_id: str
    scope: str
    loop_count: int
    by_stage: dict
    approved_count: int
    rejected_count: int
    pending_review_count: int
    requires_human_approval: bool
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
    loop_event_count: int
    loop_count: int
    review_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
