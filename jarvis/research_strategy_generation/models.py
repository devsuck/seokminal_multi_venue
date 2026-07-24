"""Research Strategy Generation Intelligence 자료형 (P29) — 후보 생성 전용. **동작 없음.**

역사적 지식(P10~P28)에서 연구 전략 후보·가설을 생성한다: 생성 세션·후보·가설·신규성 분석·증거·생성 리포트. **후보를
만든다 — 선택·승인·배포·실행·거래·자본 배분을 하지 않는다.** GENERATED ≠ SELECTED · CANDIDATE ≠ STRATEGY · CANDIDATE ≠
DEPLOYMENT. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 rsg_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 생성 세션 생애주기(5) — 이벤트 소싱 ──
S_CREATED = "CREATED"
S_GENERATING = "GENERATING"
S_ANALYZED = "ANALYZED"
S_CONCLUDED = "CONCLUDED"
S_ARCHIVED = "ARCHIVED"
SESSION_STATES = (S_CREATED, S_GENERATING, S_ANALYZED, S_CONCLUDED, S_ARCHIVED)
SESSION_TRANSITIONS = {
    S_CREATED: {S_GENERATING},
    S_GENERATING: {S_GENERATING, S_ANALYZED},
    S_ANALYZED: {S_ANALYZED, S_CONCLUDED},
    S_CONCLUDED: {S_ARCHIVED, S_GENERATING},
    S_ARCHIVED: set(),
}

# ── 후보 생애주기(5) — 이벤트 소싱, 사람 검토, 선택 없음 ──
C_PROPOSED = "PROPOSED"
C_ANALYZED = "ANALYZED"
C_NOVELTY_CHECKED = "NOVELTY_CHECKED"
C_REVIEWED = "REVIEWED"
C_ARCHIVED = "ARCHIVED"
CANDIDATE_STATES = (C_PROPOSED, C_ANALYZED, C_NOVELTY_CHECKED, C_REVIEWED, C_ARCHIVED)
CANDIDATE_TRANSITIONS = {
    C_PROPOSED: {C_ANALYZED},
    C_ANALYZED: {C_ANALYZED, C_NOVELTY_CHECKED},
    C_NOVELTY_CHECKED: {C_NOVELTY_CHECKED, C_REVIEWED},
    C_REVIEWED: {C_REVIEWED, C_ARCHIVED},
    C_ARCHIVED: set(),
}

# ── 후보 범주 ──
CANDIDATE_CATEGORIES = ("ALPHA", "RISK", "PORTFOLIO", "REGIME", "EXECUTION_RESEARCH", "DATA")
# ── 신규성 등급 ──
NOVELTY_LEVELS = ("NOVEL", "INCREMENTAL", "DUPLICATE")
# ── 증거 유형 ──
EVIDENCE_TYPES = ("HISTORICAL", "SIMULATED", "PATTERN", "LESSON")

# ── 아티팩트 유형 ──
ART_SESSION = "SESSION"
ART_CANDIDATE = "CANDIDATE"
ART_HYPOTHESIS = "HYPOTHESIS"
ART_NOVELTY = "NOVELTY"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인·선택) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "SELECT_STRATEGY", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
    "SELECT", "PROMOTE", "AUTO_SELECT_CANDIDATE",
})


class ImmutableCandidateError(Exception):
    """불변 후보(중복 genesis) 위반."""


class IllegalSessionTransition(Exception):
    """유효하지 않은 세션 전이 — 차단."""


class IllegalCandidateTransition(Exception):
    """유효하지 않은 후보 전이 — 차단."""


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


# ── 결정적 ID (SG* 스킴) ──
def session_id(objective) -> str:
    return _id("SGS", objective)


def session_event_id(sess, to, seq) -> str:
    return _id("SGE", sess, to, seq)


def candidate_id(sess, statement) -> str:
    return _id("SGC", sess, statement)


def candidate_event_id(cand, to, seq) -> str:
    return _id("SGD", cand, to, seq)


def hypothesis_id(cand, hypothesis) -> str:
    return _id("SGH", cand, hypothesis)


def novelty_id(cand, seq) -> str:
    return _id("SGN", cand, seq)


def evidence_id(cand, evidence_ref, seq) -> str:
    return _id("SGV", cand, evidence_ref, seq)


def report_id(scope, created_at) -> str:
    return _id("SGR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("SGA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_session_transition(frm, to) -> bool:
    return to in SESSION_TRANSITIONS.get(frm, set())


def can_candidate_transition(frm, to) -> bool:
    return to in CANDIDATE_TRANSITIONS.get(frm, set())


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


def _tokens(text) -> set:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in str(text)).split() if t}


def jaccard(a, b) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 0.0
    union = len(ta | tb)
    return round(len(ta & tb) / union, 6) if union else 0.0


def novelty_score(statement, prior_statements) -> float:
    """기존 후보 대비 신규성 점수(1 - 최대 유사도, 결정적). 0..1."""
    if not prior_statements:
        return 1.0
    max_sim = max(jaccard(statement, p) for p in prior_statements)
    return round(1.0 - max_sim, 6)


def classify_novelty(score) -> str:
    """신규성 점수 → 등급(결정적)."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "DUPLICATE"
    if s >= 0.7:
        return "NOVEL"
    if s >= 0.3:
        return "INCREMENTAL"
    return "DUPLICATE"


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
class SessionEventRecord:
    session_event_id: str
    session_id: str
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
class CandidateEventRecord:
    candidate_event_id: str
    candidate_id: str
    session_id: str
    category: str
    statement: str
    source_refs: list
    is_selected: bool  # 항상 False — 생성만, 자동 선택 없음
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
class HypothesisRecord:
    hypothesis_id: str
    candidate_id: str
    hypothesis: str
    rationale: str
    expected_signal: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class NoveltyRecord:
    novelty_id: str
    candidate_id: str
    score: float
    level: str
    compared_count: int
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    candidate_id: str
    evidence_ref: str
    evidence_type: str
    source_layer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GenerationReportRecord:
    report_id: str
    scope: str
    session_count: int
    candidate_count: int
    reviewed_candidate_count: int
    hypothesis_count: int
    novelty_count: int
    evidence_count: int
    category_distribution: dict
    novelty_distribution: dict
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
class GenerationSummary:
    timestamp: str
    session_event_count: int
    session_count: int
    candidate_event_count: int
    candidate_count: int
    hypothesis_count: int
    novelty_count: int
    evidence_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
