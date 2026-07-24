"""Multi-Agent Research Collaboration 자료형 (P19) — 협업·토론·합의·검토 조정·기록 전용. **실행 없음.**

연구 에이전트 협업·참여·메시지·제안·동료검토·합의·갈등·사람 검토를 조정·기록만 한다. **거래·전략 배포·권한 부여·자동
실행·자동 승인을 하지 않는다.** COLLABORATE ≠ EXECUTE · CONSENSUS ≠ APPROVAL · REVIEW ≠ DEPLOYMENT. 불변·append-
only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장은 rcol_ 접두사. P10.6 agent_governance 는 READ ONLY 참조.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 협업 생애주기(6) ──
C_CREATED = "CREATED"
C_FORMING = "FORMING"
C_ACTIVE = "ACTIVE"
C_REVIEWING = "REVIEWING"
C_COMPLETED = "COMPLETED"
C_ARCHIVED = "ARCHIVED"
COLLAB_STATES = (C_CREATED, C_FORMING, C_ACTIVE, C_REVIEWING, C_COMPLETED, C_ARCHIVED)
COLLAB_TRANSITIONS = {
    C_CREATED: {C_FORMING},
    C_FORMING: {C_FORMING, C_ACTIVE},
    C_ACTIVE: {C_ACTIVE, C_REVIEWING},
    C_REVIEWING: {C_REVIEWING, C_ACTIVE, C_COMPLETED},
    C_COMPLETED: {C_ARCHIVED},
    C_ARCHIVED: set(),
}

# ── 참여 생애주기(6) ──
P_INVITED = "INVITED"
P_ACCEPTED = "ACCEPTED"
P_ACTIVE = "ACTIVE"
P_PAUSED = "PAUSED"
P_REMOVED = "REMOVED"
P_COMPLETED = "COMPLETED"
PARTICIPATION_STATES = (P_INVITED, P_ACCEPTED, P_ACTIVE, P_PAUSED, P_REMOVED, P_COMPLETED)
PARTICIPATION_TRANSITIONS = {
    P_INVITED: {P_ACCEPTED, P_REMOVED},
    P_ACCEPTED: {P_ACTIVE, P_REMOVED},
    P_ACTIVE: {P_ACTIVE, P_PAUSED, P_COMPLETED, P_REMOVED},
    P_PAUSED: {P_ACTIVE, P_REMOVED, P_COMPLETED},
    P_COMPLETED: set(),
    P_REMOVED: set(),
}

# ── 제안 생애주기(6) ──
PR_DRAFT = "DRAFT"
PR_SUBMITTED = "SUBMITTED"
PR_DISCUSSION = "DISCUSSION"
PR_REVIEWED = "REVIEWED"
PR_ACCEPTED = "ACCEPTED"
PR_REJECTED = "REJECTED"
PROPOSAL_STATES = (PR_DRAFT, PR_SUBMITTED, PR_DISCUSSION, PR_REVIEWED, PR_ACCEPTED, PR_REJECTED)
PROPOSAL_TRANSITIONS = {
    PR_DRAFT: {PR_SUBMITTED},
    PR_SUBMITTED: {PR_DISCUSSION},
    PR_DISCUSSION: {PR_DISCUSSION, PR_REVIEWED},
    PR_REVIEWED: {PR_ACCEPTED, PR_REJECTED},
    PR_ACCEPTED: set(),
    PR_REJECTED: set(),
}

# ── 합의 생애주기(5) ──
CS_OPEN = "OPEN"
CS_DISCUSSION = "DISCUSSION"
CS_TENTATIVE = "TENTATIVE"
CS_REVIEWED = "REVIEWED"
CS_RECORDED = "RECORDED"
CONSENSUS_STATES = (CS_OPEN, CS_DISCUSSION, CS_TENTATIVE, CS_REVIEWED, CS_RECORDED)
CONSENSUS_TRANSITIONS = {
    CS_OPEN: {CS_DISCUSSION},
    CS_DISCUSSION: {CS_DISCUSSION, CS_TENTATIVE},
    CS_TENTATIVE: {CS_TENTATIVE, CS_REVIEWED, CS_DISCUSSION},
    CS_REVIEWED: {CS_RECORDED, CS_DISCUSSION},
    CS_RECORDED: set(),
}

# ── 갈등 생애주기(4) ──
CF_OPEN = "OPEN"
CF_ANALYZING = "ANALYZING"
CF_RESOLVED = "RESOLVED"
CF_DOCUMENTED = "DOCUMENTED"
CONFLICT_STATES = (CF_OPEN, CF_ANALYZING, CF_RESOLVED, CF_DOCUMENTED)
CONFLICT_TRANSITIONS = {
    CF_OPEN: {CF_ANALYZING},
    CF_ANALYZING: {CF_ANALYZING, CF_RESOLVED},
    CF_RESOLVED: {CF_DOCUMENTED},
    CF_DOCUMENTED: set(),
}

# ── 사람 검토 생애주기(5) ──
HR_REQUESTED = "REQUESTED"
HR_ASSIGNED = "ASSIGNED"
HR_UNDER_REVIEW = "UNDER_REVIEW"
HR_COMMENTED = "COMMENTED"
HR_CLOSED = "CLOSED"
HUMAN_REVIEW_STATES = (HR_REQUESTED, HR_ASSIGNED, HR_UNDER_REVIEW, HR_COMMENTED, HR_CLOSED)
HUMAN_REVIEW_TRANSITIONS = {
    HR_REQUESTED: {HR_ASSIGNED},
    HR_ASSIGNED: {HR_UNDER_REVIEW},
    HR_UNDER_REVIEW: {HR_COMMENTED},
    HR_COMMENTED: {HR_CLOSED},
    HR_CLOSED: set(),
}

# ── 열거형 ──
MESSAGE_TYPES = ("HYPOTHESIS", "EVIDENCE", "QUESTION", "CRITIQUE", "RESULT", "SUMMARY")
REVIEW_CATEGORIES = ("methodology", "data_quality", "robustness", "reproducibility", "risk")
CONFLICT_TYPES = ("DATA", "METHOD", "ASSUMPTION", "INTERPRETATION", "RESULT")
CONSENSUS_POSITIONS = ("AGREEMENT", "DISAGREEMENT", "UNCERTAINTY", "MINORITY_OPINION")

# ── 아티팩트 유형 ──
ART_COLLABORATION = "COLLABORATION"
ART_MESSAGE = "MESSAGE"
ART_PROPOSAL = "PROPOSAL"
ART_REVIEW = "REVIEW"
ART_CONSENSUS = "CONSENSUS"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·자동조치) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "DEPLOY_MODEL",
    "DEPLOY", "PROMOTE_MODEL", "CHANGE_PERMISSION", "GRANT_PERMISSION", "AUTO_EXECUTE",
    "AUTO_APPROVE", "APPROVE_FOR_TRADING", "TRADE", "EXECUTE", "ALLOCATE", "PROMOTE",
})


class ImmutableRecordError(Exception):
    """불변 레코드(중복) 위반."""


class IllegalTransition(Exception):
    """유효하지 않은 상태 전이 — 차단."""


class UnknownEntityError(Exception):
    """미등록 엔티티 참조."""


class HumanReviewRequired(Exception):
    """사람 검토/기록된 합의 없이 승인 시도 — 차단(자동 승인 없음)."""


class ReviewerRequired(Exception):
    """검토자 신원 없이 배정 시도 — 차단(익명 승인 없음)."""


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


def _id(tag: str, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (CX* 스킴) ──
def collaboration_id(name: str) -> str:
    return _id("CXB", name)


def collab_event_id(cid: str, to: str, seq: int) -> str:
    return _id("CXL", cid, to, seq)


def participant_id(cid: str, agent: str) -> str:
    return _id("CXU", cid, agent)


def participation_event_id(pid: str, to: str, seq: int) -> str:
    return _id("CXP", pid, to, seq)


def message_id(cid: str, author: str, seq: int) -> str:
    return _id("CXM", cid, author, seq)


def proposal_id(cid: str, title: str) -> str:
    return _id("CXO", cid, title)


def proposal_event_id(pid: str, to: str, seq: int) -> str:
    return _id("CXR", pid, to, seq)


def review_id(reviewer: str, target: str, category: str, seq: int) -> str:
    return _id("CXV", reviewer, target, category, seq)


def consensus_id(cid: str, topic: str) -> str:
    return _id("CXG", cid, topic)


def consensus_event_id(cons: str, to: str, seq: int) -> str:
    return _id("CXS", cons, to, seq)


def conflict_id(cid: str, ctype: str, seq: int) -> str:
    return _id("CXK", cid, ctype, seq)


def conflict_event_id(conf: str, to: str, seq: int) -> str:
    return _id("CXC", conf, to, seq)


def human_review_id(cid: str, subject: str, seq: int) -> str:
    return _id("CXW", cid, subject, seq)


def human_review_event_id(hr: str, to: str, seq: int) -> str:
    return _id("CXH", hr, to, seq)


def report_id(cid: str, scope: str, generated_at: str) -> str:
    return _id("CXN", cid, scope, generated_at)


def artifact_id(atype: str, ref: str) -> str:
    return _id("CXF", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_collab_transition(frm: str, to: str) -> bool:
    return _can(COLLAB_TRANSITIONS, frm, to)


def can_participation_transition(frm: str, to: str) -> bool:
    return _can(PARTICIPATION_TRANSITIONS, frm, to)


def can_proposal_transition(frm: str, to: str) -> bool:
    return _can(PROPOSAL_TRANSITIONS, frm, to)


def can_consensus_transition(frm: str, to: str) -> bool:
    return _can(CONSENSUS_TRANSITIONS, frm, to)


def can_conflict_transition(frm: str, to: str) -> bool:
    return _can(CONFLICT_TRANSITIONS, frm, to)


def can_human_review_transition(frm: str, to: str) -> bool:
    return _can(HUMAN_REVIEW_TRANSITIONS, frm, to)


def detect_cycle_check(edges: list) -> bool:
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
class CollabEventRecord:
    collab_event_id: str
    collaboration_id: str
    name: str
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
class ParticipationEventRecord:
    participation_event_id: str
    participant_id: str
    collaboration_id: str
    agent_id: str
    role: str
    specialization: str
    from_state: str
    to_state: str
    contribution: str
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
    collaboration_id: str
    author_agent: str
    message_type: str
    payload_hash: str
    reference_artifacts: list
    metadata: dict
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProposalEventRecord:
    proposal_event_id: str
    proposal_id: str
    collaboration_id: str
    author_agent: str
    title: str
    from_state: str
    to_state: str
    note: str
    basis: str          # 승인 근거 참조(human_review_id 또는 consensus_id), 없으면 ""
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    collaboration_id: str
    reviewer: str
    target: str
    category: str
    score: float
    comments: str
    evidence: list
    is_binding: bool    # 항상 False — 연구 메타데이터일 뿐
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConsensusEventRecord:
    consensus_event_id: str
    consensus_id: str
    collaboration_id: str
    topic: str
    from_state: str
    to_state: str
    positions: dict     # {AGREEMENT: n, DISAGREEMENT: n, UNCERTAINTY: n, MINORITY_OPINION: [...]}
    is_approval: bool   # 항상 False — 합의 ≠ 승인/배포/거래
    note: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConflictEventRecord:
    conflict_event_id: str
    conflict_id: str
    collaboration_id: str
    conflict_type: str
    from_state: str
    to_state: str
    description: str
    outcome: str        # RESOLVED/DOCUMENTED 시 결과 기록(선택 강제 없음)
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HumanReviewEventRecord:
    human_review_event_id: str
    human_review_id: str
    collaboration_id: str
    subject: str
    reviewer: str       # 신원 필수(익명 승인 금지)
    from_state: str
    to_state: str
    comment: str
    occurred_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CollaborationReportRecord:
    report_id: str
    collaboration_id: str
    scope: str
    collaboration_state: str
    participant_count: int
    message_count: int
    proposal_count: int
    review_count: int
    consensus_count: int
    conflict_count: int
    human_review_count: int
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
class CollaborationSummary:
    timestamp: str
    collab_event_count: int
    participation_event_count: int
    message_count: int
    proposal_event_count: int
    review_count: int
    consensus_event_count: int
    conflict_event_count: int
    human_review_event_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
