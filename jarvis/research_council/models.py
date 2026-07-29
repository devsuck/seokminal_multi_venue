"""Multi-Agent Research Council 자료형 (P11.6) — 다중 AI 연구 에이전트 협의체. **협의·기록 전용.**

여러 연구 에이전트(Data·Strategy·Alpha·Portfolio·Risk·Simulation·Reviewer·Knowledge)가 연구 토론을 조율한다.
**실행하지 않는다. 배포를 승인하지 않는다. 상위 연구를 수정하지 않는다.** 협의체는 권고만 할 수 있다 —
전략 승인·배포·거래·자본 할당·권한 변경·설정 변경·주문 실행·브로커 호출·포트폴리오 수정 없음.
COUNCIL ≠ EXECUTION · CONSENSUS ≠ APPROVAL · RECOMMENDATION ≠ DEPLOYMENT. 불변·append-only·해시체인·이벤트 소싱.
물리 원장은 cnl_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 협의체 멤버(에이전트 역할, 8) ──
ROLE_DATA = "DATA"
ROLE_STRATEGY = "STRATEGY"
ROLE_ALPHA = "ALPHA"
ROLE_PORTFOLIO = "PORTFOLIO"
ROLE_RISK = "RISK"
ROLE_SIMULATION = "SIMULATION"
ROLE_REVIEWER = "REVIEWER"
ROLE_KNOWLEDGE = "KNOWLEDGE"
AGENT_ROLES = (ROLE_DATA, ROLE_STRATEGY, ROLE_ALPHA, ROLE_PORTFOLIO, ROLE_RISK, ROLE_SIMULATION,
               ROLE_REVIEWER, ROLE_KNOWLEDGE)

# ── 협의체(세션) 생애주기 상태(6) ──
S_CREATED = "CREATED"
S_ACTIVE = "ACTIVE"
S_DISCUSSING = "DISCUSSING"
S_VOTING = "VOTING"
S_CONSENSUS = "CONSENSUS"
S_CLOSED = "CLOSED"
COUNCIL_STATES = (S_CREATED, S_ACTIVE, S_DISCUSSING, S_VOTING, S_CONSENSUS, S_CLOSED)

ALLOWED_TRANSITIONS = {
    S_CREATED: {S_ACTIVE},
    S_ACTIVE: {S_DISCUSSING, S_CLOSED},
    S_DISCUSSING: {S_VOTING, S_ACTIVE},
    S_VOTING: {S_CONSENSUS, S_DISCUSSING},
    S_CONSENSUS: {S_CLOSED},
    S_CLOSED: set(),
}

# ── 논증 입장 ──
STANCE_FOR = "FOR"
STANCE_AGAINST = "AGAINST"
STANCES = (STANCE_FOR, STANCE_AGAINST)

# ── 투표 선택 ──
VOTE_FOR = "FOR"
VOTE_AGAINST = "AGAINST"
VOTE_ABSTAIN = "ABSTAIN"
VOTE_CHOICES = (VOTE_FOR, VOTE_AGAINST, VOTE_ABSTAIN)

# ── 합의 결과(4) ──
C_UNANIMOUS = "UNANIMOUS"
C_MAJORITY = "MAJORITY"
C_SPLIT = "SPLIT"
C_NO_CONSENSUS = "NO_CONSENSUS"
CONSENSUS_OUTCOMES = (C_UNANIMOUS, C_MAJORITY, C_SPLIT, C_NO_CONSENSUS)

# ── 아티팩트(계보) 유형 ──
ART_COUNCIL = "COUNCIL"
ART_SESSION = "SESSION"
ART_ARGUMENT = "ARGUMENT"
ART_CONSENSUS = "CONSENSUS"
ART_SUMMARY = "SUMMARY"

# ── 금지(실행·승인·배포) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "APPROVE_STRATEGY", "DEPLOY", "DEPLOY_STRATEGY", "TRADE", "ALLOCATE", "ALLOCATE_CAPITAL",
    "MODIFY_PERMISSION", "CHANGE_CONFIG", "EXECUTE", "EXECUTE_ORDER", "CALL_BROKER",
    "MODIFY_PORTFOLIO", "ACTIVATE", "APPROVE",
})


class ImmutableCouncilError(Exception):
    """불변 협의체 위반."""


class ImmutableParticipantError(Exception):
    """불변 참가자 위반."""


class ImmutableArgumentError(Exception):
    """불변 논증 위반."""


class ImmutableVoteError(Exception):
    """불변 투표 위반."""


class ImmutableConsensusError(Exception):
    """불변 합의 위반."""


class ImmutableMinorityError(Exception):
    """불변 소수의견 위반."""


class ImmutableSummaryError(Exception):
    """불변 요약 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class InvalidAgentRole(Exception):
    """미등록 에이전트 역할."""


class InvalidStance(Exception):
    """미등록 논증 입장."""


class InvalidVoteChoice(Exception):
    """미등록 투표 선택."""


class IllegalSessionTransition(Exception):
    """허용되지 않은 세션 상태 전이."""


class UnknownCouncilError(Exception):
    """미등록 협의체 참조."""


class UnknownSessionError(Exception):
    """미등록 세션 참조."""


class UnknownArgumentError(Exception):
    """미등록 논증 참조."""


class SessionStateError(Exception):
    """현재 상태에서 허용되지 않은 작업."""


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
def council_id(name: str) -> str:
    return "CNL:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def session_id(council: str, topic: str) -> str:
    return "CNS:" + hashlib.sha1(input_digest(council, topic).encode()).hexdigest()[:12]


def session_event_id(session: str, to_state: str, seq: int = 0) -> str:
    return "CSE:" + hashlib.sha1(
        input_digest(session, to_state, seq).encode()).hexdigest()[:12]


def participant_id(session: str, agent: str) -> str:
    return "CNP:" + hashlib.sha1(input_digest(session, agent).encode()).hexdigest()[:12]


def discussion_id(session: str, participant: str, message: str) -> str:
    return "CND:" + hashlib.sha1(
        input_digest(session, participant, message).encode()).hexdigest()[:12]


def argument_id(session: str, participant: str, claim: str) -> str:
    return "CNA:" + hashlib.sha1(
        input_digest(session, participant, claim).encode()).hexdigest()[:12]


def vote_id(session: str, topic: str, participant: str) -> str:
    return "CNV:" + hashlib.sha1(
        input_digest(session, topic, participant).encode()).hexdigest()[:12]


def consensus_id(session: str, topic: str) -> str:
    return "CNC:" + hashlib.sha1(input_digest(session, topic).encode()).hexdigest()[:12]


def minority_id(session: str, consensus: str, participant: str) -> str:
    return "CNM:" + hashlib.sha1(
        input_digest(session, consensus, participant).encode()).hexdigest()[:12]


def summary_id(session: str, topic: str) -> str:
    return "CNU:" + hashlib.sha1(input_digest(session, topic).encode()).hexdigest()[:12]


def report_id(council: str, scope: str, generated_at: str) -> str:
    return "CNR:" + hashlib.sha1(
        input_digest(council, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "CNT:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 협의 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def tally_votes(choices: list) -> dict:
    """투표 집계(결정적): FOR/AGAINST/ABSTAIN 카운트."""
    out = {VOTE_FOR: 0, VOTE_AGAINST: 0, VOTE_ABSTAIN: 0}
    for c in choices:
        if c in out:
            out[c] += 1
    return out


def consensus_outcome(choices: list) -> str:
    """합의 결과 계산(결정적). **CONSENSUS ≠ APPROVAL.**

    결정표=FOR+AGAINST. 결정표 0 → NO_CONSENSUS. 한쪽 0 → UNANIMOUS. 동수 → SPLIT. 그 외 → MAJORITY.
    """
    t = tally_votes(choices)
    decisive = t[VOTE_FOR] + t[VOTE_AGAINST]
    if decisive == 0:
        return C_NO_CONSENSUS
    if min(t[VOTE_FOR], t[VOTE_AGAINST]) == 0:
        return C_UNANIMOUS
    if t[VOTE_FOR] == t[VOTE_AGAINST]:
        return C_SPLIT
    return C_MAJORITY


def winning_stance(choices: list) -> str:
    """다수 입장(결정적). 동수/무효면 빈 문자열."""
    t = tally_votes(choices)
    if t[VOTE_FOR] == t[VOTE_AGAINST]:
        return ""
    return STANCE_FOR if t[VOTE_FOR] > t[VOTE_AGAINST] else STANCE_AGAINST


def detect_cycle(edges: list) -> list:
    """방향 그래프 순환 탐지(DFS, 결정적). 첫 순환 경로 또는 []."""
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
class CouncilRecord:
    council_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionEventRecord:
    session_event_id: str
    session_id: str
    council_id: str
    topic: str
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
class ParticipantRecord:
    participant_id: str
    session_id: str
    agent_name: str
    role: str
    invited_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DiscussionRecord:
    discussion_id: str
    session_id: str
    participant: str
    message: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ArgumentRecord:
    argument_id: str
    session_id: str
    participant: str
    claim: str
    stance: str
    parent_argument: str
    is_counter: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VoteRecord:
    vote_id: str
    session_id: str
    topic: str
    participant: str
    choice: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConsensusRecord:
    consensus_id: str
    session_id: str
    topic: str
    outcome: str
    for_count: int
    against_count: int
    abstain_count: int
    winning_stance: str
    participant_count: int
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MinorityRecord:
    minority_id: str
    session_id: str
    consensus_id: str
    participant: str
    stance: str
    opinion: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SummaryRecord:
    summary_id: str
    session_id: str
    topic: str
    outcome: str
    recommendation: str
    argument_count: int
    vote_count: int
    minority_count: int
    is_decision: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CouncilReportRecord:
    report_id: str
    council_id: str
    scope: str
    session_count: int
    consensus_count: int
    outcome_distribution: dict
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
    session_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CouncilSummary:
    timestamp: str
    council_count: int
    session_event_count: int
    participant_count: int
    discussion_count: int
    argument_count: int
    vote_count: int
    consensus_count: int
    minority_count: int
    summary_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
