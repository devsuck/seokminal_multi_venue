"""Research Conflict Resolution 자료형 (P11.9) — 연구 충돌 분석·해소 계층. **리뷰·분석 전용.**

여러 AI 연구 에이전트가 서로 다른 결론·가설·평가·권고를 낼 때 이견을 기록·분석·해소한다. **거래 전략 선택·배포
승인·연구 결과 수정·에이전트 무시·행위 실행을 하지 않는다.** 모든 충돌은 원본 주장·증거 출처·에이전트 신원·
추론 이력·소수의견을 보존한다. 삭제·덮어쓰기 없음. CONFLICT ≠ EXECUTION · RESOLUTION ≠ APPROVAL · CONSENSUS ≠
DEPLOYMENT. 불변·append-only·이벤트 소싱·해시체인. 물리 원장은 crf_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 충돌 생애주기 상태(5) ──
C_DETECTED = "DETECTED"
C_ANALYZING = "ANALYZING"
C_DISCUSSING = "DISCUSSING"
C_RESOLVED = "RESOLVED"
C_ARCHIVED = "ARCHIVED"
CONFLICT_STATES = (C_DETECTED, C_ANALYZING, C_DISCUSSING, C_RESOLVED, C_ARCHIVED)

ALLOWED_TRANSITIONS = {
    C_DETECTED: {C_ANALYZING},
    C_ANALYZING: {C_DISCUSSING},
    C_DISCUSSING: {C_RESOLVED, C_ANALYZING},
    C_RESOLVED: {C_ARCHIVED},
    C_ARCHIVED: set(),
}
# 주장/증거/포지션 추가 가능 상태(RESOLVED/ARCHIVED 이전 — 이력 동결 전).
OPEN_STATES = frozenset({C_DETECTED, C_ANALYZING, C_DISCUSSING})

# ── 해소 유형(4) ──
R_CONSENSUS = "CONSENSUS"
R_MAJORITY = "MAJORITY"
R_EVIDENCE_SUPERIOR = "EVIDENCE_SUPERIOR"
R_UNRESOLVED = "UNRESOLVED"
RESOLUTION_TYPES = (R_CONSENSUS, R_MAJORITY, R_EVIDENCE_SUPERIOR, R_UNRESOLVED)

# ── 증거 유형 ──
EV_METRIC = "METRIC"
EV_BACKTEST = "BACKTEST"
EV_CITATION = "CITATION"
EV_REVIEW = "REVIEW"
EV_DATA = "DATA"
EV_REPLAY = "REPLAY"
EV_EXTERNAL = "EXTERNAL"
EVIDENCE_TYPES = (EV_METRIC, EV_BACKTEST, EV_CITATION, EV_REVIEW, EV_DATA, EV_REPLAY, EV_EXTERNAL)

# ── 아티팩트(계보) 유형 ──
ART_CONFLICT = "CONFLICT"
ART_CLAIM = "CLAIM"
ART_SESSION = "SESSION"
ART_OUTCOME = "OUTCOME"
ART_REPORT = "REPORT"

# ── 금지(실행·승인·수정) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "APPROVE_FOR_TRADING", "MODIFY_STRATEGY",
    "MODIFY_MODEL", "CHANGE_PERMISSION", "CHANGE_CONFIG", "APPROVE", "ACTIVATE", "OVERRIDE",
})


class ImmutableConflictError(Exception):
    """불변 충돌 위반."""


class ImmutableClaimError(Exception):
    """불변 주장 위반."""


class ImmutableEvidenceError(Exception):
    """불변 증거 위반."""


class ImmutablePositionError(Exception):
    """불변 에이전트 포지션 위반."""


class ImmutableOutcomeError(Exception):
    """불변 해소 결과 위반."""


class ImmutableMinorityError(Exception):
    """불변 소수의견 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class InvalidResolutionType(Exception):
    """미등록 해소 유형."""


class InvalidEvidenceType(Exception):
    """미등록 증거 유형."""


class IllegalConflictTransition(Exception):
    """허용되지 않은 충돌 상태 전이."""


class ConflictClosedError(Exception):
    """종료된 충돌(RESOLVED/ARCHIVED) 이력 편집 시도."""


class UnknownRegistryError(Exception):
    """미등록 레지스트리 참조."""


class UnknownConflictError(Exception):
    """미등록 충돌 참조."""


class UnknownClaimError(Exception):
    """미등록 주장 참조."""


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
def registry_id(name: str) -> str:
    return "CRG:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def conflict_id(registry: str, subject: str) -> str:
    return "CFC:" + hashlib.sha1(input_digest(registry, subject).encode()).hexdigest()[:12]


def conflict_event_id(conflict: str, to_state: str, seq: int) -> str:
    return "CFE:" + hashlib.sha1(input_digest(conflict, to_state, seq).encode()).hexdigest()[:12]


def claim_id(conflict: str, agent: str, conclusion: str) -> str:
    return "CFM:" + hashlib.sha1(
        input_digest(conflict, agent, conclusion).encode()).hexdigest()[:12]


def evidence_id(claim: str, layer: str, ref: str) -> str:
    return "CFV:" + hashlib.sha1(input_digest(claim, layer, ref).encode()).hexdigest()[:12]


def position_id(conflict: str, agent: str) -> str:
    return "CFP:" + hashlib.sha1(input_digest(conflict, agent).encode()).hexdigest()[:12]


def session_id(conflict: str, seq: int) -> str:
    return "CFS:" + hashlib.sha1(input_digest(conflict, seq).encode()).hexdigest()[:12]


def resolution_id(conflict: str, session: str) -> str:
    return "CFO:" + hashlib.sha1(input_digest(conflict, session).encode()).hexdigest()[:12]


def minority_id(conflict: str, agent: str) -> str:
    return "CFN:" + hashlib.sha1(input_digest(conflict, agent).encode()).hexdigest()[:12]


def consensus_id(conflict: str, session: str) -> str:
    return "CFK:" + hashlib.sha1(input_digest(conflict, session).encode()).hexdigest()[:12]


def report_id(conflict: str, scope: str, generated_at: str) -> str:
    return "CFR:" + hashlib.sha1(
        input_digest(conflict, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "CFA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def derive_resolution(support_tally: dict, evidence_tally: dict) -> tuple:
    """포지션 지지·증거 집계로 해소 유형·주도 주장 계산(결정적).

    반환 (resolution_type, leading_claim). 지지 0 → UNRESOLVED. 한 주장이 전 지지 독점 → CONSENSUS.
    단독 최다 지지 → MAJORITY. 지지 동수인데 증거 단독 최다 → EVIDENCE_SUPERIOR. 그 외 → UNRESOLVED.
    """
    if not support_tally or sum(support_tally.values()) == 0:
        return R_UNRESOLVED, ""
    max_sup = max(support_tally.values())
    leaders = sorted(c for c, v in support_tally.items() if v == max_sup)
    nonzero = [c for c, v in support_tally.items() if v > 0]
    if len(nonzero) == 1:
        return R_CONSENSUS, nonzero[0]
    if len(leaders) == 1:
        return R_MAJORITY, leaders[0]
    # 지지 동수 → 증거로 판정
    ev_among = {c: evidence_tally.get(c, 0) for c in leaders}
    max_ev = max(ev_among.values()) if ev_among else 0
    ev_leaders = sorted(c for c, v in ev_among.items() if v == max_ev)
    if max_ev > 0 and len(ev_leaders) == 1:
        return R_EVIDENCE_SUPERIOR, ev_leaders[0]
    return R_UNRESOLVED, ""


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
class RegistryRecord:
    registry_id: str
    name: str
    mandate: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConflictEventRecord:
    event_id: str
    conflict_id: str
    registry_id: str
    subject: str
    description: str
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
class ClaimRecord:
    claim_id: str
    conflict_id: str
    agent: str
    conclusion: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    claim_id: str
    conflict_id: str
    layer: str
    ref: str
    evidence_type: str
    detail: str
    read_only: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PositionRecord:
    position_id: str
    conflict_id: str
    agent: str
    backed_claim: str
    rationale: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    conflict_id: str
    facilitator: str
    method: str
    started_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OutcomeRecord:
    resolution_id: str
    conflict_id: str
    session_id: str
    resolution_type: str
    winning_claim: str
    computed_type: str
    rationale: str
    decided_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConsensusRecord:
    consensus_id: str
    conflict_id: str
    session_id: str
    support_tally: dict
    evidence_tally: dict
    leading_claim: str
    computed_type: str
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
    conflict_id: str
    agent: str
    backed_claim: str
    opinion: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConflictReportRecord:
    report_id: str
    conflict_id: str
    scope: str
    lifecycle_state: str
    claim_count: int
    position_count: int
    evidence_count: int
    minority_count: int
    resolution_type: str
    winning_claim: str
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
    conflict_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConflictSummary:
    timestamp: str
    registry_count: int
    conflict_event_count: int
    claim_count: int
    evidence_count: int
    position_count: int
    session_count: int
    outcome_count: int
    minority_count: int
    consensus_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
