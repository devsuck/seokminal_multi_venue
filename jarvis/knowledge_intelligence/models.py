"""Advanced Research Knowledge Intelligence 자료형 (P10.27) — 지식 그래프를 상위 인텔리전스로 확장. 분석 전용.

P10.5 Research Knowledge Graph·P10.21 Governance Memory·P10.26 Research Lifecycle 를 **READ ONLY** 로 참조
(파일 기반, import 없음)해 연구 유사도·실패 실험 검색·전략 패밀리 클러스터링·모순 탐지·지식 추천을 수행하고
지식 인사이트·유사도 리포트·클러스터·모순·연구 패턴을 남긴다. **권고는 정보용일 뿐, 자동 선택·승인·배포 없음.**
RECOMMENDATION ≠ ACTION · SIMILARITY ≠ SELECTION · CLUSTER ≠ APPROVAL · INSIGHT ≠ DEPLOYMENT. 불변·append-only·
결정적. 물리 원장은 ki_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 인사이트 유형 ──
INSIGHT_SIMILARITY = "SIMILARITY"
INSIGHT_CLUSTER = "CLUSTER"
INSIGHT_CONTRADICTION = "CONTRADICTION"
INSIGHT_PATTERN = "PATTERN"
INSIGHT_RECOMMENDATION = "RECOMMENDATION"
INSIGHT_TYPES = (INSIGHT_SIMILARITY, INSIGHT_CLUSTER, INSIGHT_CONTRADICTION, INSIGHT_PATTERN,
                 INSIGHT_RECOMMENDATION)

# ── 모순 스탠스 ──
SUPPORTS = "SUPPORTS"
REFUTES = "REFUTES"
STANCES = (SUPPORTS, REFUTES)

# ── 연구 패턴 유형 ──
P_REPEATED_FAILURE = "repeated_failure"
P_COMMON_FAMILY = "common_family"
P_RECURRING_CONTRADICTION = "recurring_contradiction"
P_CONVERGENT_APPROACH = "convergent_approach"
PATTERN_TYPES = (P_REPEATED_FAILURE, P_COMMON_FAMILY, P_RECURRING_CONTRADICTION,
                 P_CONVERGENT_APPROACH)

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_OBJECT = "OBJECT"
NODE_SIMILARITY = "SIMILARITY"
NODE_CLUSTER = "CLUSTER"
NODE_CONTRADICTION = "CONTRADICTION"
NODE_PATTERN = "PATTERN"
NODE_INSIGHT = "INSIGHT"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_OBJECT, NODE_SIMILARITY, NODE_CLUSTER, NODE_CONTRADICTION,
              NODE_PATTERN, NODE_INSIGHT, NODE_REPORT)

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_OBJECT = "OBJECT"
ART_SIMILARITY = "SIMILARITY"
ART_CLUSTER = "CLUSTER"
ART_CONTRADICTION = "CONTRADICTION"
ART_PATTERN = "PATTERN"
ART_INSIGHT = "INSIGHT"
ART_REPORT = "REPORT"

# ── 패턴 신뢰도 파라미터 ──
_OCC_SATURATION = 3.0
_MEMBER_SATURATION = 3.0


class ImmutableSimilarityError(Exception):
    """불변 유사도 기록 위반."""


class ImmutableClusterError(Exception):
    """불변 클러스터 위반."""


class ImmutableContradictionError(Exception):
    """불변 모순 기록 위반."""


class ImmutablePatternError(Exception):
    """불변 연구 패턴 위반."""


class ImmutableInsightError(Exception):
    """불변 지식 인사이트 위반."""


class InvalidInsightType(Exception):
    """미등록 인사이트 유형."""


class InvalidStance(Exception):
    """미등록 모순 스탠스."""


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


def members_hash(members: list) -> str:
    return _digest(sorted(members or []))


# ── 결정적 ID ──
def _pair_key(a: str, b: str) -> tuple:
    """무방향 쌍 정규화(정렬)."""
    return tuple(sorted([a, b]))


def similarity_id(ref_a: str, ref_b: str) -> str:
    a, b = _pair_key(ref_a, ref_b)
    return "KIS:" + hashlib.sha1(input_digest(a, b).encode()).hexdigest()[:12]


def cluster_id(family_key: str, members: list) -> str:
    return "KIC:" + hashlib.sha1(
        input_digest(family_key, sorted(members or [])).encode()).hexdigest()[:12]


def contradiction_id(subject: str) -> str:
    return "KIX:" + hashlib.sha1(input_digest(subject).encode()).hexdigest()[:12]


def pattern_id(pattern_type: str, subject: str) -> str:
    return "KIP:" + hashlib.sha1(
        input_digest(pattern_type, subject).encode()).hexdigest()[:12]


def insight_id(insight_type: str, subject: str, reference: str) -> str:
    return "KII:" + hashlib.sha1(
        input_digest(insight_type, subject, reference).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "KIR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "KIA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def jaccard(tokens_a, tokens_b) -> float:
    """토큰 집합 Jaccard 유사도(0~1, 결정적). **SIMILARITY ≠ SELECTION.**"""
    a, b = set(tokens_a or []), set(tokens_b or [])
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(inter / union, 8) if union else 0.0


def pattern_confidence(occurrences: int, member_count: int) -> float:
    base = min(1.0, float(max(0, occurrences)) / _OCC_SATURATION)
    breadth = min(1.0, float(max(0, member_count)) / _MEMBER_SATURATION)
    return round(0.6 * base + 0.4 * breadth, 8)


def connected_components(edges: list, nodes: list | None = None) -> list:
    """무방향 연결 요소(전략 패밀리 클러스터, 결정적). 각 요소는 정렬된 노드 리스트."""
    adj: dict = {}
    allnodes: set = set(nodes or [])
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
        allnodes.add(a)
        allnodes.add(b)
    seen: set = set()
    out: list = []
    for n in sorted(allnodes):
        if n in seen:
            continue
        stack = [n]
        comp: set = set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            seen.add(x)
            for y in adj.get(x, ()):
                if y not in comp:
                    stack.append(y)
        out.append(sorted(comp))
    return sorted(out, key=lambda c: (-len(c), c))


def cluster_by_tokens(items: list, min_shared: int = 1) -> list:
    """items=[(ref, [tokens])] → 공유 토큰(≥min_shared) 기준 클러스터. 결정적."""
    refs = [it[0] for it in items]
    tokmap = {it[0]: set(it[1] or []) for it in items}
    edges: list = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            if len(tokmap[a] & tokmap[b]) >= min_shared:
                edges.append((a, b))
    return connected_components(edges, refs)


def detect_contradictions(claims: list) -> list:
    """claims=[{ref, subject, stance}] → subject 별 SUPPORTS/REFUTES 상충 탐지. 결정적."""
    by_subject: dict = {}
    for c in claims or []:
        by_subject.setdefault(c.get("subject"), {SUPPORTS: [], REFUTES: []})
        st = c.get("stance")
        if st in (SUPPORTS, REFUTES):
            by_subject[c.get("subject")][st].append(c.get("ref"))
    out: list = []
    for subject in sorted(by_subject):
        sup = sorted(set(by_subject[subject][SUPPORTS]))
        ref = sorted(set(by_subject[subject][REFUTES]))
        if sup and ref:
            out.append({"subject": subject, "supporting": sup, "refuting": ref})
    return out


def detect_cycle(edges: list) -> list:
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
class SimilarityRecord:
    similarity_id: str
    ref_a: str
    ref_b: str
    score: float
    method: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ClusterRecord:
    cluster_id: str
    family_key: str
    members: list
    size: int
    members_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContradictionRecord:
    contradiction_id: str
    subject: str
    supporting: list
    refuting: list
    detail: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchPattern:
    pattern_id: str
    pattern_type: str
    subject: str
    occurrences: int
    related_refs: list
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeInsight:
    insight_id: str
    insight_type: str
    subject: str
    reference: str
    content: str
    supporting_refs: list
    confidence: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeReport:
    report_id: str
    scope: str
    insight_count: int
    insight_type_distribution: dict
    similarity_count: int
    cluster_count: int
    largest_cluster_size: int
    contradiction_count: int
    pattern_count: int
    pattern_type_distribution: dict
    recommendation_count: int
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeArtifact:
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
class KnowledgeSummary:
    timestamp: str
    insight_count: int
    insight_type_distribution: dict
    similarity_count: int
    cluster_count: int
    contradiction_count: int
    pattern_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
