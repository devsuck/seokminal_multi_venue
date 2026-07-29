"""Production Readiness & Deployment Governance 자료형 (P21) — 준비성 검증·승인 기록·감사 전용. **배포 없음.**

연구 결과가 운영으로 넘어가기 전 배포 준비성 검증·승인 기록·전환 조건을 기록·검증·감사만 한다. **실제 주문·live
trading·portfolio mutation·capital allocation·자동 배포·자동 승인을 하지 않는다.** VALIDATED ≠ DEPLOYED ·
READY ≠ LIVE. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 pd_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 후보 상태 머신(6) ──
S_REGISTERED = "REGISTERED"
S_CHECKING = "CHECKING"
S_READY_FOR_REVIEW = "READY_FOR_REVIEW"
S_REVIEWED = "REVIEWED"
S_READY_FOR_DEPLOYMENT = "READY_FOR_DEPLOYMENT"  # 연구 상태일 뿐 — 배포 아님
S_ARCHIVED = "ARCHIVED"
CANDIDATE_STATES = (S_REGISTERED, S_CHECKING, S_READY_FOR_REVIEW, S_REVIEWED,
                    S_READY_FOR_DEPLOYMENT, S_ARCHIVED)
CANDIDATE_TRANSITIONS = {
    S_REGISTERED: {S_CHECKING},
    S_CHECKING: {S_CHECKING, S_READY_FOR_REVIEW},
    S_READY_FOR_REVIEW: {S_REVIEWED, S_CHECKING},
    S_REVIEWED: {S_READY_FOR_DEPLOYMENT, S_CHECKING},
    S_READY_FOR_DEPLOYMENT: {S_ARCHIVED},
    S_ARCHIVED: set(),
}

# ── 리뷰 상태 머신(4) ──
R_PENDING = "PENDING"
R_APPROVED = "APPROVED"
R_REJECTED = "REJECTED"
R_REQUEST_CHANGE = "REQUEST_CHANGE"
REVIEW_STATES = (R_PENDING, R_APPROVED, R_REJECTED, R_REQUEST_CHANGE)
REVIEW_TRANSITIONS = {
    R_PENDING: {R_APPROVED, R_REJECTED, R_REQUEST_CHANGE},
    R_APPROVED: set(),
    R_REJECTED: set(),
    R_REQUEST_CHANGE: set(),
}
_DECISION_MAP = {"APPROVE": R_APPROVED, "REJECT": R_REJECTED, "REQUEST_CHANGE": R_REQUEST_CHANGE}

# ── 체크리스트 범주(9) ──
CHECKLIST_CATEGORIES = ("research_quality", "data_quality", "model_validation",
                        "backtest_validation", "simulation_validation", "risk_validation",
                        "lineage_validation", "reproducibility", "security_review")
CHECK_STATUSES = ("PASS", "WARNING", "FAILED")

# ── 요구사항 유형 ──
REQUIREMENT_TYPES = ("minimum_validation_period", "minimum_oos_result", "maximum_drawdown_limit",
                     "minimum_data_quality", "simulation_pass_required", "human_review_required")

# ── 리스크 등급 ──
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# ── 아티팩트 유형 ──
ART_CANDIDATE = "CANDIDATE"
ART_CHECK = "CHECK"
ART_REVIEW = "REVIEW"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·승격·권한) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "PROMOTE_MODEL", "CHANGE_PERMISSION", "ENABLE_EXECUTION", "DEPLOY", "ACTIVATE", "EXECUTE",
    "TRADE", "ALLOCATE", "AUTO_APPROVE", "AUTO_DEPLOY",
})


class ImmutableCandidateError(Exception):
    """불변 후보(중복) 위반."""


class IllegalCandidateTransition(Exception):
    """유효하지 않은 후보 상태 전이 — 차단."""


class IllegalReviewTransition(Exception):
    """유효하지 않은 리뷰 상태 전이 — 차단."""


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


class ReviewerRequired(Exception):
    """검토자 없이 리뷰/승인 시도 — 차단(자동 승인 없음)."""


class ApprovalRequired(Exception):
    """승인된 리뷰 없이 배포 준비 전이 시도 — 차단(자동 승인 없음)."""


class MissingEvidenceError(Exception):
    """증거 없이 준비성 체크 시도 — 차단(evidence_required)."""


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


def metadata_hash(metadata) -> str:
    return _digest(metadata or {})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (PD* 스킴, PDR 회피) ──
def candidate_id(source_layer, source_reference) -> str:
    return _id("PDC", source_layer, source_reference)


def transition_id(cand, to, seq) -> str:
    return _id("PDT", cand, to, seq)


def check_id(cand, category, seq) -> str:
    return _id("PDK", cand, category, seq)


def requirement_id(cand, req_type, seq) -> str:
    return _id("PDQ", cand, req_type, seq)


def review_id(cand, subject) -> str:
    return _id("PDV", cand, subject)


def review_event_id(rev, to, seq) -> str:
    return _id("PDW", rev, to, seq)


def risk_id(cand, seq) -> str:
    return _id("PDS", cand, seq)


def report_id(cand, scope, generated_at) -> str:
    return _id("PDG", cand, scope, generated_at)


def artifact_id(atype, ref) -> str:
    return _id("PDA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_candidate_transition(frm, to) -> bool:
    return to in CANDIDATE_TRANSITIONS.get(frm, set())


def can_review_transition(frm, to) -> bool:
    return to in REVIEW_TRANSITIONS.get(frm, set())


def normalize_decision(decision) -> str | None:
    return _DECISION_MAP.get((decision or "").strip().upper())


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
class DeploymentCandidateRecord:
    candidate_id: str
    source_layer: str
    source_reference: str
    strategy_reference: str
    model_reference: str
    portfolio_reference: str
    metadata_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TransitionRecord:
    transition_id: str
    candidate_id: str
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
class ReadinessCheckRecord:
    check_id: str
    candidate_id: str
    category: str
    status: str
    evidence: list
    evidence_required: bool  # 항상 True
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RequirementRecord:
    requirement_id: str
    candidate_id: str
    requirement_type: str
    target: str
    actual: str
    met: bool
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReviewEventRecord:
    review_event_id: str
    review_id: str
    candidate_id: str
    subject: str
    reviewer_id: str          # 필수 — 검토자 없으면 승인/전이 불가
    from_state: str
    to_state: str
    decision: str
    comments: str
    is_automatic: bool        # 항상 False — 자동 승인 없음
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskAssessmentRecord:
    risk_id: str
    candidate_id: str
    level: str
    factors: list
    detail: str
    is_binding: bool          # 항상 False — 평가·기록일 뿐
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReadinessReportRecord:
    report_id: str
    candidate_id: str
    scope: str
    candidate_state: str
    check_summary: dict
    requirement_summary: dict
    review_decision: str
    risk_level: str
    deployed: bool            # 항상 False — READY_FOR_DEPLOYMENT ≠ DEPLOYED
    is_binding: bool          # 항상 False
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
class ReadinessSummary:
    timestamp: str
    candidate_count: int
    transition_count: int
    check_count: int
    requirement_count: int
    review_event_count: int
    risk_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
