"""Research Literature Intelligence 자료형 (P11.3) — 외부 지식(논문)과 연구 시스템 연결. **읽기·기록 전용.**

논문 메타데이터·개념 추출·전략 아이디어 추출·인용 그래프·연구 비교를 수행하고 Papers·Concepts·Citations·
Knowledge Links 를 남긴다. 연구 OS 는 **READ ONLY** 로만 참조(파일 기반, import 없음). **자동 전략 생성 없음 —
전략 아이디어는 정보용 개념일 뿐이다.** LITERATURE ≠ STRATEGY · IDEA ≠ DEPLOYMENT · CITATION ≠ EXECUTION.
불변·append-only·해시체인. 물리 원장은 rli_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 개념 종류 ──
CONCEPT = "CONCEPT"
METHOD = "METHOD"
STRATEGY_IDEA = "STRATEGY_IDEA"
METRIC = "METRIC"
DATASET = "DATASET"
MODEL = "MODEL"
CONCEPT_TYPES = (CONCEPT, METHOD, STRATEGY_IDEA, METRIC, DATASET, MODEL)

# ── 지식 링크 종류 ──
LINK_PAPER_CONCEPT = "PAPER_CONCEPT"
LINK_PAPER_OS = "PAPER_OS"
LINK_CONCEPT_OS = "CONCEPT_OS"
LINK_PAPER_PAPER = "PAPER_PAPER"
LINK_TYPES = (LINK_PAPER_CONCEPT, LINK_PAPER_OS, LINK_CONCEPT_OS, LINK_PAPER_PAPER)

# ── 논문 출처 ──
SOURCE_EXTERNAL = "EXTERNAL"

# ── 자동 전략 생성 금지 동사(탐지용) ──
FORBIDDEN_VERBS = frozenset({
    "CREATE_STRATEGY", "REGISTER_STRATEGY", "DEPLOY", "EXECUTE", "TRADE", "ALLOCATE",
    "ACTIVATE", "PROMOTE", "APPROVE",
})


class ImmutablePaperError(Exception):
    """불변 논문 위반."""


class ImmutableConceptError(Exception):
    """불변 개념 위반."""


class ImmutableCitationError(Exception):
    """불변 인용 위반."""


class ImmutableLinkError(Exception):
    """불변 지식 링크 위반."""


class ImmutableComparisonError(Exception):
    """불변 비교 위반."""


class InvalidConceptType(Exception):
    """미등록 개념 종류."""


class InvalidLinkType(Exception):
    """미등록 링크 종류."""


class SelfCitationError(Exception):
    """자기 인용 — 거부."""


class UnknownPaperError(Exception):
    """미등록 논문 참조."""


class UnknownConceptError(Exception):
    """미등록 개념 참조."""


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


# ── 정규화·지문 ──
def normalize(text: str) -> str:
    """제목/이름 정규화(소문자·공백정리) — 중복 탐지용."""
    return " ".join((text or "").lower().split())


def fingerprint(text: str) -> str:
    return hashlib.sha1(normalize(text).encode()).hexdigest()[:16]


def paper_key(doi: str, title: str, year) -> str:
    """논문 식별 키: doi 우선, 없으면 정규화 제목+연도."""
    if doi:
        return "doi:" + normalize(doi)
    return f"title:{fingerprint(title)}:{year}"


# ── 결정적 ID ──
def paper_id(key: str) -> str:
    return "RLP:" + hashlib.sha1(input_digest(key).encode()).hexdigest()[:12]


def concept_id(name: str) -> str:
    return "RLC:" + hashlib.sha1(input_digest(fingerprint(name)).encode()).hexdigest()[:12]


def citation_id(citing: str, cited: str) -> str:
    return "RLX:" + hashlib.sha1(input_digest(citing, cited).encode()).hexdigest()[:12]


def link_id(link_type: str, source: str, target: str) -> str:
    return "RLK:" + hashlib.sha1(
        input_digest(link_type, source, target).encode()).hexdigest()[:12]


def comparison_id(a: str, b: str) -> str:
    x, y = tuple(sorted([a, b]))
    return "RLM:" + hashlib.sha1(input_digest(x, y).encode()).hexdigest()[:12]


# ── 결정적 분석 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def jaccard(a, b) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 0.0
    u = len(sa | sb)
    return round(len(sa & sb) / u, 8) if u else 0.0


def detect_cycle(edges: list) -> list:
    """방향 그래프(citing→cited) 순환 탐지(DFS, 결정적). 첫 순환 경로 또는 []."""
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


def ancestors(edges: list, node: str) -> list:
    """node 가 (전이적으로) 인용하는 모든 논문(지적 계보). 결정적."""
    adj: dict = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
    seen: set = set()
    stack = [node]
    while stack:
        x = stack.pop()
        for nxt in sorted(adj.get(x, ())):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return sorted(seen)


def roots(nodes: list, edges: list) -> list:
    """인용 진입 없는 논문(아무도 인용하지 않은 = 최신/말단 인용자)."""
    cited = {b for _, b in edges}
    return sorted(n for n in nodes if n not in cited)


def leaves(nodes: list, edges: list) -> list:
    """인용 진출 없는 논문(아무것도 인용하지 않는 = 기초/원천)."""
    citing = {a for a, _ in edges}
    return sorted(n for n in nodes if n not in citing)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    key: str
    title: str
    authors: list
    year: int
    venue: str
    doi: str
    url: str
    fingerprint: str
    source: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConceptRecord:
    concept_id: str
    name: str
    concept_type: str
    description: str
    parent_concept: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CitationRecord:
    citation_id: str
    citing_paper: str
    cited_paper: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeLinkRecord:
    link_id: str
    link_type: str
    source_id: str
    target_id: str
    relation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ComparisonRecord:
    comparison_id: str
    paper_a: str
    paper_b: str
    shared_concepts: list
    only_a: list
    only_b: list
    similarity: float
    summary: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LiteratureSummary:
    timestamp: str
    paper_count: int
    concept_count: int
    citation_count: int
    link_count: int
    comparison_count: int
    strategy_idea_count: int

    def to_dict(self) -> dict:
        return asdict(self)
