"""Research Knowledge Evolution & Memory Intelligence 자료형 (P27) — 지식 메모리 전용. **동작 없음.**

역사적 연구 지식을 진화하는 메모리 시스템으로 결합한다: 발견 보존·반복 패턴 추적·실험 간 교훈 연결·재사용 지식 식별·
연구 진화 이력 유지. **이것은 지식 메모리 시스템이다.** 거래 결정·전략 배포·실험 실행·모델 수정·연구 산출 승인·자본 배분을
하지 않는다. MEMORY ASSISTS RESEARCH · MEMORY DOES NOT DECIDE. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적.
물리 원장 rmi_ 접두사. 상위 계층(P10~P26)은 READ ONLY. P10.5 KG·P20 Research Memory 소유권 불변(중복 없음).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 메모리 생애주기(5) — 이벤트 소싱 ──
M_CREATED = "CREATED"
M_CONNECTED = "CONNECTED"
M_REINFORCED = "REINFORCED"
M_EVOLVED = "EVOLVED"
M_ARCHIVED = "ARCHIVED"
MEMORY_STATES = (M_CREATED, M_CONNECTED, M_REINFORCED, M_EVOLVED, M_ARCHIVED)
MEMORY_TRANSITIONS = {
    M_CREATED: {M_CONNECTED},
    M_CONNECTED: {M_CONNECTED, M_REINFORCED, M_EVOLVED, M_ARCHIVED},  # ARCHIVED: 폐기(DEPRECATED) 경로
    M_REINFORCED: {M_REINFORCED, M_EVOLVED, M_ARCHIVED},
    M_EVOLVED: {M_EVOLVED, M_REINFORCED, M_ARCHIVED},
    M_ARCHIVED: set(),
}

# ── 메모리 범주 ──
MEMORY_CATEGORIES = ("DISCOVERY", "LESSON", "FAILURE", "SUCCESS", "PATTERN", "INSIGHT")
# ── 패턴 유형 ──
PATTERN_TYPES = ("SUCCESS_PATTERN", "FAILURE_PATTERN", "ROBUSTNESS_PATTERN", "DATA_PATTERN")
# ── 진화 변경 유형 ──
CHANGE_TYPES = ("CONNECTED", "REINFORCED", "WEAKENED", "DEPRECATED")
# ── 변경 유형 → 메모리 생애주기 목표 상태 ──
CHANGE_TO_STATE = {
    "CONNECTED": M_CONNECTED,
    "REINFORCED": M_REINFORCED,
    "WEAKENED": M_EVOLVED,
    "DEPRECATED": M_ARCHIVED,
}

# ── 아티팩트 유형 ──
ART_MEMORY = "MEMORY"
ART_LESSON = "LESSON"
ART_PATTERN = "PATTERN"
ART_SUCCESS = "SUCCESS"
ART_FAILURE = "FAILURE"
ART_RETRIEVAL = "RETRIEVAL"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인·선택) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "SELECT_STRATEGY", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
    "SELECT", "PROMOTE", "AUTOMATIC_RECOMMENDATION", "AUTOMATIC_STRATEGY_CHOICE",
})


class ImmutableMemoryError(Exception):
    """불변 메모리(중복 genesis) 위반."""


class IllegalMemoryTransition(Exception):
    """유효하지 않은 메모리 전이 — 차단."""


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


def memory_content_hash(content) -> str:
    return _digest({"content": content})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (KM* 스킴) ──
def memory_id(source_reference, category, content) -> str:
    return _id("KMM", source_reference, category, content)


def memory_event_id(mem, to, seq) -> str:
    return _id("KME", mem, to, seq)


def pattern_id(pattern_type, signature) -> str:
    return _id("KMP", pattern_type, signature)


def lesson_id(origin, lesson) -> str:
    return _id("KML", origin, lesson)


def success_id(origin, summary) -> str:
    return _id("KMS", origin, summary)


def failure_id(origin, summary) -> str:
    return _id("KMF", origin, summary)


def evolution_event_id(mem, change_type, seq) -> str:
    return _id("KMV", mem, change_type, seq)


def retrieval_id(query_context, seq) -> str:
    return _id("KMR", query_context, seq)


def report_id(scope, created_at) -> str:
    return _id("KMO", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("KMA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_memory_transition(frm, to) -> bool:
    return to in MEMORY_TRANSITIONS.get(frm, set())


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


def evolve_confidence(base, changes) -> float:
    """기저 중요도 + 진화 변경 로그(REINFORCED +0.1 / WEAKENED -0.1 / DEPRECATED →0)로 신뢰도 산출(결정적).

    **레코드 변경 없음 — 이벤트 로그를 재생해 파생값만 계산한다.**
    """
    if any(c == "DEPRECATED" for c in changes):
        return 0.0
    conf = clamp01(base)
    for c in changes:
        if c == "REINFORCED":
            conf += 0.1
        elif c == "WEAKENED":
            conf -= 0.1
    return clamp01(conf)


def _tokens(text) -> set:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in str(text)).split() if t}


def jaccard(a, b) -> float:
    """토큰 자카드 유사도(0..1, 결정적)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return round(inter / union, 6) if union else 0.0


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
class MemoryEventRecord:
    memory_event_id: str
    memory_id: str
    source_reference: str
    category: str
    content_hash: str
    importance_score: float
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
class LessonRecord:
    lesson_id: str
    origin: str
    lesson: str
    evidence: dict
    impact: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    pattern_type: str
    signature: str
    occurrences: int
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SuccessRecord:
    success_id: str
    origin: str
    summary: str
    evidence: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureRecord:
    failure_id: str
    origin: str
    summary: str
    evidence: dict
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionEventRecord:
    event_id: str
    memory_id: str
    change_type: str
    related_memory: str
    reason: str
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalRecord:
    retrieval_id: str
    query_context: str
    memory_refs: list
    scores: dict
    is_recommendation: bool  # 항상 False — 참조만, 자동 추천/선택 없음
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionReportRecord:
    report_id: str
    scope: str
    memory_count: int
    active_memory_count: int
    archived_memory_count: int
    lesson_count: int
    pattern_count: int
    success_count: int
    failure_count: int
    evolution_event_count: int
    retrieval_count: int
    category_distribution: dict
    change_distribution: dict
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
class MemoryIntelligenceSummary:
    timestamp: str
    memory_event_count: int
    memory_count: int
    lesson_count: int
    pattern_count: int
    success_count: int
    failure_count: int
    evolution_event_count: int
    retrieval_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
