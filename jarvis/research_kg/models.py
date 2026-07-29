"""Research Knowledge Graph 자료형 (P10.5) — 연구 엔티티·관계·계보·유사도·스냅샷 전용.

P9.8~P10.4 연구 원장을 **READ ONLY** 로 연결해 지식 그래프를 만든다. **분석·검색·관계 추적만.**
실행/배포/주문/자본배분/모델적용 권한 없음. VALIDATED ≠ DEPLOYED · RANKED ≠ SELECTED ·
CONNECTED ≠ ENABLED. 엔티티는 그래프 노드(연구 참조)이고 관계·계보는 서술적 링크일 뿐이다.
불변·append-only 해시체인·결정적. 물리 원장은 kg_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── Entity 유형 ──
STRATEGY = "STRATEGY"
SIGNAL = "SIGNAL"
FEATURE = "FEATURE"
DATASET = "DATASET"
MODEL = "MODEL"
EXPERIMENT = "EXPERIMENT"
BACKTEST = "BACKTEST"
VALIDATION = "VALIDATION"
PORTFOLIO = "PORTFOLIO"
RISK_ANALYSIS = "RISK_ANALYSIS"

ENTITY_TYPES = (STRATEGY, SIGNAL, FEATURE, DATASET, MODEL, EXPERIMENT, BACKTEST,
                VALIDATION, PORTFOLIO, RISK_ANALYSIS)

# ── Entity 생명주기 상태머신(서술적 — 실행 상태 아님) ──
REGISTERED = "REGISTERED"
LINKED = "LINKED"
ANALYZED = "ANALYZED"
SNAPSHOTTED = "SNAPSHOTTED"

LIFECYCLE_STATES = (REGISTERED, LINKED, ANALYZED, SNAPSHOTTED)

ALLOWED_TRANSITIONS = {
    "": {REGISTERED},
    REGISTERED: {LINKED},
    LINKED: {ANALYZED},
    ANALYZED: {SNAPSHOTTED},
    SNAPSHOTTED: set(),
}

# ── Relationship 유형 ──
USES = "USES"                    # STRATEGY  uses        SIGNAL
DEPENDS_ON = "DEPENDS_ON"        # SIGNAL    depends_on   FEATURE
DERIVED_FROM = "DERIVED_FROM"    # FEATURE   derived_from DATASET
EVALUATES = "EVALUATES"          # EXPERIMENT evaluates   STRATEGY
VALIDATES = "VALIDATES"          # BACKTEST  validates    EXPERIMENT
CONTAINS = "CONTAINS"            # PORTFOLIO contains     STRATEGY
ANALYZES = "ANALYZES"            # RISK_ANALYSIS analyzes PORTFOLIO

RELATIONSHIP_TYPES = (USES, DEPENDS_ON, DERIVED_FROM, EVALUATES, VALIDATES, CONTAINS, ANALYZES)

# (source_type, rel_type) -> 허용 target_type 집합. 그 외 관계는 차단.
RELATIONSHIP_RULES = {
    (STRATEGY, USES): {SIGNAL},
    (SIGNAL, DEPENDS_ON): {FEATURE},
    (FEATURE, DERIVED_FROM): {DATASET},
    (EXPERIMENT, EVALUATES): {STRATEGY},
    (BACKTEST, VALIDATES): {EXPERIMENT},
    (PORTFOLIO, CONTAINS): {STRATEGY},
    (RISK_ANALYSIS, ANALYZES): {PORTFOLIO},
}

# 계보 정방향 흐름(Dataset→Feature→Signal→Strategy→Experiment→Backtest→Portfolio).
LINEAGE_FLOW = (DATASET, FEATURE, SIGNAL, STRATEGY, EXPERIMENT, BACKTEST, PORTFOLIO)

# ── 유사도 라벨(자동 제거/선택 아님 — 서술적) ──
SIMILAR = "SIMILAR"
RELATED = "RELATED"
DISTINCT = "DISTINCT"
SIMILARITY_HIGH = 0.7
SIMILARITY_LOW = 0.3

# ── Artifact 유형 ──
ART_ENTITY = "ENTITY"
ART_RELATIONSHIP = "RELATIONSHIP"
ART_SNAPSHOT = "SNAPSHOT"


class IllegalTransition(Exception):
    """차단된 엔티티 생명주기 전이."""


class ImmutableEntityError(Exception):
    """불변 엔티티 위반(동일 entity_id 내용 상이)."""


class InvalidRelationship(Exception):
    """규칙 위반 관계(허용되지 않은 source_type/rel_type/target_type)."""


class CycleError(Exception):
    """관계/계보에 순환을 유발하는 링크 — 차단."""


class UnknownEntity(Exception):
    """미등록 엔티티 참조."""


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def relationship_allowed(source_type: str, rel_type: str, target_type: str) -> bool:
    return target_type in RELATIONSHIP_RULES.get((source_type, rel_type), set())


def similarity_level(score: float) -> str:
    s = float(score)
    if s >= SIMILARITY_HIGH:
        return SIMILAR
    if s >= SIMILARITY_LOW:
        return RELATED
    return DISTINCT


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


def metadata_hash(metadata: dict) -> str:
    return _digest(dict(metadata or {}))


# ── 결정적 ID ──
def entity_id(entity_type: str, source_layer: str, source_id: str) -> str:
    return "KGE:" + hashlib.sha1(
        input_digest(entity_type, source_layer, source_id).encode()).hexdigest()[:12]


def entity_event_id(entity_key: str, from_state: str, to_state: str) -> str:
    return "KEE:" + hashlib.sha1(
        input_digest(entity_key, from_state, to_state).encode()).hexdigest()[:12]


def relationship_id(source_entity: str, rel_type: str, target_entity: str) -> str:
    return "KGR:" + hashlib.sha1(
        input_digest(source_entity, rel_type, target_entity).encode()).hexdigest()[:12]


def lineage_edge_id(from_entity: str, to_entity: str, edge_type: str) -> str:
    return "KGL:" + hashlib.sha1(
        input_digest(from_entity, to_entity, edge_type).encode()).hexdigest()[:12]


def similarity_report_id(entity_a: str, entity_b: str) -> str:
    a, b = sorted((entity_a, entity_b))
    return "KGS:" + hashlib.sha1(input_digest(a, b).encode()).hexdigest()[:12]


def snapshot_id(graph_hash: str) -> str:
    return "KGN:" + hashlib.sha1(input_digest(graph_hash).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "KGA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def graph_hash(entity_ids: list, edges: list) -> str:
    """노드·엣지 집합의 결정적 지문. 동일 그래프 상태 → 동일 해시."""
    return _digest({"nodes": sorted(set(entity_ids or [])),
                    "edges": sorted({tuple(e) for e in (edges or [])})})


# ── 그래프 알고리즘(읽기전용 분석) ──
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


def connected_components(nodes: list, edges: list) -> list:
    """무방향 연결요소(연구 클러스터) — 정렬된 노드 리스트들의 리스트."""
    adj: dict = {n: set() for n in nodes}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen: set = set()
    comps: list = []
    for start in sorted(adj):
        if start in seen:
            continue
        stack = [start]
        comp: set = set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(adj.get(n, ()) - seen)
        comps.append(sorted(comp))
    return sorted(comps, key=lambda c: (-len(c), c))


def longest_path_depth(start: str, edges: list) -> int:
    """DAG 상 start 에서 도달 가능한 최장 경로 길이(엣지 수). 순환이면 -1."""
    graph: dict = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    if detect_cycle(edges):
        return -1
    memo: dict = {}

    def depth(node) -> int:
        if node in memo:
            return memo[node]
        best = 0
        for nxt in graph.get(node, ()):
            best = max(best, 1 + depth(nxt))
        memo[node] = best
        return best

    return depth(start)


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class EntityEvent:
    """엔티티 등록·상태 전이 이벤트(이벤트 소싱). entity_id 는 연구 노드 정체성."""
    event_id: str
    entity_key: str                 # == entity_id
    entity_id: str
    entity_type: str
    source_layer: str               # 원본 레이어(data_governance/alpha_intelligence/...)
    source_id: str                  # 원본 레이어의 참조 ID(문자열만)
    metadata_hash: str
    from_state: str
    to_state: str
    status: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    source_entity: str
    source_type: str
    rel_type: str
    target_entity: str
    target_type: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LineageEdge:
    lineage_id: str
    from_entity: str
    to_entity: str
    edge_type: str                  # 정방향 계보 흐름 라벨
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimilarityReport:
    report_id: str
    entity_a: str
    entity_b: str
    entity_type: str
    score: float                    # 0~1 서술적 유사도
    level: str                      # SIMILAR | RELATED | DISTINCT (자동 선택 아님)
    basis: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphSnapshot:
    snapshot_id: str
    node_count: int
    edge_count: int
    lineage_edge_count: int
    similarity_count: int
    entity_distribution: dict
    layer_distribution: dict
    graph_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphArtifact:
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
class ResearchGraphReport:
    timestamp: str
    total_entities: int
    entity_distribution: dict
    layer_distribution: dict
    state_distribution: dict
    relationship_count: int
    lineage_edge_count: int
    snapshot_count: int
    similarity_count: int
    most_connected_signals: list        # [{entity_id, degree}] 상위
    most_reused_datasets: list          # [{entity_id, reuse}] 상위
    strategy_dependency_depth: dict      # {strategy_entity_id: depth}
    research_clusters: int
    orphan_entities: list               # 관계 없는 엔티티
    broken_lineage: list                # 미존재 엔티티 참조 계보

    def to_dict(self) -> dict:
        return asdict(self)
