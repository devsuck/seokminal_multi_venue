"""Research Insight Intelligence & Interpretation 자료형 (P28) — 해석 지능 전용. **동작 없음.**

P27 장기 연구 메모리를 연구 통찰·맥락 설명·관계 해석·연구 방향 신호·지식 요약으로 변환한다: 패턴이 왜 존재하는지 이해·역사적
증거 요약·연구 공백 식별·단절된 발견 연결·연구자 이해 향상. **이 계층은 전략 선택·가설 승인·모델 배포·실험 실행·거래·자본
배분을 하지 않는다.** INSIGHT ≠ DECISION · INSIGHT ≠ RECOMMENDATION · INSIGHT ≠ STRATEGY. 불변·append-only·SHA256
해시체인·이벤트 소싱·결정적. 물리 원장 rii_ 접두사. 상위 계층(P10~P27)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 통찰 생애주기(5) — 이벤트 소싱 ──
I_CREATED = "CREATED"
I_SUPPORTED = "SUPPORTED"
I_CONNECTED = "CONNECTED"
I_REVIEWED = "REVIEWED"
I_ARCHIVED = "ARCHIVED"
INSIGHT_STATES = (I_CREATED, I_SUPPORTED, I_CONNECTED, I_REVIEWED, I_ARCHIVED)
INSIGHT_TRANSITIONS = {
    I_CREATED: {I_SUPPORTED},
    I_SUPPORTED: {I_SUPPORTED, I_CONNECTED},
    I_CONNECTED: {I_CONNECTED, I_REVIEWED},
    I_REVIEWED: {I_REVIEWED, I_ARCHIVED, I_CONNECTED},
    I_ARCHIVED: set(),
}

# ── 통찰 범주 ──
INSIGHT_CATEGORIES = ("DISCOVERY", "PATTERN", "RISK", "LIMITATION", "OPPORTUNITY", "CONTRADICTION")
# ── 관계 유형 ──
RELATION_TYPES = ("SUPPORTS", "CONTRADICTS", "EXTENDS", "DEPENDS_ON")
# ── 연구 공백 유형 ──
GAP_TYPES = ("MISSING_VALIDATION", "INSUFFICIENT_SAMPLES", "CONTRADICTORY_RESULTS",
             "UNEXPLORED_AREA")
# ── 증거 유형 ──
EVIDENCE_TYPES = ("SUPPORTING", "CONFLICTING")

# ── 아티팩트 유형 ──
ART_CONTEXT = "CONTEXT"
ART_INSIGHT = "INSIGHT"
ART_INTERPRETATION = "INTERPRETATION"
ART_GAP = "RESEARCH_GAP"
ART_RELATIONSHIP = "RELATIONSHIP"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인·선택) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "SELECT_STRATEGY", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
    "SELECT", "PROMOTE", "APPROVE_HYPOTHESIS", "RECOMMEND_STRATEGY",
})


class ImmutableInsightError(Exception):
    """불변 통찰(중복 genesis) 위반."""


class IllegalInsightTransition(Exception):
    """유효하지 않은 통찰 전이 — 차단."""


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


# ── 결정적 ID (II* 스킴) ──
def insight_id(category, statement) -> str:
    return _id("IIN", category, statement)


def insight_event_id(ins, to, seq) -> str:
    return _id("IIE", ins, to, seq)


def context_id(domain, description) -> str:
    return _id("IIC", domain, description)


def interpretation_id(ins, seq) -> str:
    return _id("IIP", ins, seq)


def evidence_link_id(ins, evidence_ref, seq) -> str:
    return _id("IIL", ins, evidence_ref, seq)


def gap_id(gap_type, description) -> str:
    return _id("IIG", gap_type, description)


def relationship_id(source, target, relation_type) -> str:
    return _id("IIX", source, target, relation_type)


def report_id(scope, created_at) -> str:
    return _id("IIO", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("IIA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_insight_transition(frm, to) -> bool:
    return to in INSIGHT_TRANSITIONS.get(frm, set())


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


def interpret_confidence(supporting, conflicting) -> float:
    """증거 해석 신뢰도 = supporting / (supporting + conflicting) (결정적). 증거 없으면 0."""
    try:
        s = max(0, int(supporting))
        c = max(0, int(conflicting))
    except (TypeError, ValueError):
        return 0.0
    total = s + c
    if total == 0:
        return 0.0
    return round(s / total, 6)


def _tokens(text) -> set:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in str(text)).split() if t}


def jaccard(a, b) -> float:
    """토큰 자카드 유사도(0..1, 결정적)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 0.0
    union = len(ta | tb)
    return round(len(ta & tb) / union, 6) if union else 0.0


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
class InsightEventRecord:
    insight_event_id: str
    insight_id: str
    source_refs: list
    category: str
    statement: str
    confidence: float
    context_id: str
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
class ContextRecord:
    context_id: str
    domain: str
    references: list
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InterpretationRecord:
    interpretation_id: str
    insight_id: str
    evidence: dict
    explanation: str
    supporting_count: int
    conflicting_count: int
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceLinkRecord:
    evidence_link_id: str
    insight_id: str
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
class ResearchGapRecord:
    gap_id: str
    gap_type: str
    description: str
    missing_information: str
    related_insights: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RelationshipRecord:
    relationship_id: str
    source: str
    target: str
    relation_type: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InterpretationReportRecord:
    report_id: str
    scope: str
    insight_count: int
    active_insight_count: int
    reviewed_insight_count: int
    context_count: int
    interpretation_count: int
    evidence_link_count: int
    gap_count: int
    relationship_count: int
    category_distribution: dict
    relation_distribution: dict
    gap_distribution: dict
    summary: dict
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
class InsightSummary:
    timestamp: str
    insight_event_count: int
    insight_count: int
    context_count: int
    interpretation_count: int
    evidence_link_count: int
    gap_count: int
    relationship_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
