"""Research Operating System Orchestration 자료형 (P11) — 전 연구 인텔리전스 생태계 관찰·조직 전용.

P9.8~P10.15 전 계층을 **READ ONLY** 로 소비해 통합 연구 상태·교차계층 계보 지도·연구 생명주기 가시성·
시스템 건강·의존 인식·연구 활동 타임라인을 제공한다. **연구 실행·실험 시작·strategy 선택·model 배포·
config 수정·capital 배분 없음.** ORCHESTRATION ≠ EXECUTION · VISIBILITY ≠ CONTROL · STATUS ≠ APPROVAL ·
INSIGHT ≠ ACTION. 불변·append-only 해시체인·결정적. 물리 원장은 ros_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Layer 생명주기 ──
REGISTERED = "REGISTERED"
ACTIVE = "ACTIVE"
DEPRECATED = "DEPRECATED"

LAYER_STATES = (REGISTERED, ACTIVE, DEPRECATED)
LAYER_TRANSITIONS = {
    "": {REGISTERED},
    REGISTERED: {ACTIVE, DEPRECATED},
    ACTIVE: {DEPRECATED},
    DEPRECATED: set(),
}

# ── Workflow 생명주기 ──
CREATED = "CREATED"
TRACKING = "TRACKING"
COMPLETED = "COMPLETED"
ARCHIVED = "ARCHIVED"

WORKFLOW_STATES = (CREATED, TRACKING, COMPLETED, ARCHIVED)
WORKFLOW_TRANSITIONS = {
    "": {CREATED},
    CREATED: {TRACKING},
    TRACKING: {COMPLETED},
    COMPLETED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Snapshot 생명주기 ──
VERIFIED = "VERIFIED"
# CREATED / ARCHIVED 공유

SNAPSHOT_STATES = (CREATED, VERIFIED, ARCHIVED)
SNAPSHOT_TRANSITIONS = {
    "": {CREATED},
    CREATED: {VERIFIED},
    VERIFIED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 연구 워크플로 그래프 노드 유형 ──
NODE_DATASET = "DATASET"
NODE_FEATURE = "FEATURE"
NODE_SIGNAL = "SIGNAL"
NODE_STRATEGY = "STRATEGY"
NODE_PORTFOLIO = "PORTFOLIO"
NODE_MODEL = "MODEL"
NODE_EXPERIMENT = "EXPERIMENT"
NODE_SIMULATION = "SIMULATION"
NODE_CAUSAL_RESULT = "CAUSAL_RESULT"
NODE_INSIGHT = "INSIGHT"
NODE_PLAN = "PLAN"
NODE_TYPES = (NODE_DATASET, NODE_FEATURE, NODE_SIGNAL, NODE_STRATEGY, NODE_PORTFOLIO, NODE_MODEL,
              NODE_EXPERIMENT, NODE_SIMULATION, NODE_CAUSAL_RESULT, NODE_INSIGHT, NODE_PLAN)

# ── 워크플로/계보 엣지 유형 ──
PRODUCES = "PRODUCES"
USES = "USES"
VALIDATES = "VALIDATES"
EXPLAINS = "EXPLAINS"
IMPROVES = "IMPROVES"
PLANS = "PLANS"
EDGE_TYPES = (PRODUCES, USES, VALIDATES, EXPLAINS, IMPROVES, PLANS)

# ── Cross layer event 유형(예시) ──
DATASET_REGISTERED = "DATASET_REGISTERED"
EXPERIMENT_COMPLETED = "EXPERIMENT_COMPLETED"
VALIDATION_CREATED = "VALIDATION_CREATED"
INSIGHT_GENERATED = "INSIGHT_GENERATED"
EVENT_TYPES = (DATASET_REGISTERED, EXPERIMENT_COMPLETED, VALIDATION_CREATED, INSIGHT_GENERATED)

# ── System health 라벨 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"

# ── Health 가중치(합=1.0) ──
HEALTH_WEIGHTS = {
    "layer_availability": 0.25,
    "lineage_completeness": 0.20,
    "data_traceability": 0.20,
    "validation_coverage": 0.20,
    "research_reproducibility": 0.15,
}

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_WORKFLOW = "WORKFLOW"
ART_EVENT = "EVENT"
ART_SNAPSHOT = "SNAPSHOT"
ART_DEPENDENCY = "DEPENDENCY"
ART_HEALTH = "HEALTH"
ART_LINEAGE = "LINEAGE"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableLayerError(Exception):
    """불변 레이어 위반."""


class ImmutableWorkflowError(Exception):
    """불변 워크플로 위반."""


class UnknownLayer(Exception):
    """미등록 레이어 참조."""


class UnknownWorkflow(Exception):
    """미등록 워크플로 참조."""


class UnknownSnapshot(Exception):
    """미등록 스냅샷 참조."""


class InvalidWorkflowGraph(Exception):
    """유효하지 않은 워크플로 그래프(미등록 노드/엣지/순환)."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_layer(frm: str, to: str) -> bool:
    return _can(LAYER_TRANSITIONS, frm, to)


def can_transition_workflow(frm: str, to: str) -> bool:
    return _can(WORKFLOW_TRANSITIONS, frm, to)


def can_transition_snapshot(frm: str, to: str) -> bool:
    return _can(SNAPSHOT_TRANSITIONS, frm, to)


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


def ecosystem_hash(layers: list, workflow_count: int, event_count: int) -> str:
    return _digest({"layers": sorted(layers or []), "workflows": int(workflow_count),
                    "events": int(event_count)})


# ── 결정적 ID ──
def layer_id(name: str) -> str:
    return "ROL:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def layer_event_id(lid: str, frm: str, to: str) -> str:
    return "RLE:" + hashlib.sha1(input_digest(lid, frm, to).encode()).hexdigest()[:12]


def workflow_id(name: str) -> str:
    return "ROW:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def workflow_event_id(wid: str, frm: str, to: str) -> str:
    return "RWE:" + hashlib.sha1(input_digest(wid, frm, to).encode()).hexdigest()[:12]


def event_id(layer: str, event_type: str, reference_id: str) -> str:
    return "REV:" + hashlib.sha1(
        input_digest(layer, event_type, reference_id).encode()).hexdigest()[:12]


def snapshot_id(name: str, epoch: str) -> str:
    return "RSN:" + hashlib.sha1(input_digest(name, epoch).encode()).hexdigest()[:12]


def snapshot_event_id(sid: str, frm: str, to: str) -> str:
    return "RSE:" + hashlib.sha1(input_digest(sid, frm, to).encode()).hexdigest()[:12]


def dependency_id(from_layer: str, to_layer: str) -> str:
    return "ROD:" + hashlib.sha1(input_digest(from_layer, to_layer).encode()).hexdigest()[:12]


def health_report_id(snapshot_ref: str) -> str:
    return "RHR:" + hashlib.sha1(input_digest(snapshot_ref).encode()).hexdigest()[:12]


def lineage_id(from_node: str, edge_type: str, to_node: str) -> str:
    return "RLN:" + hashlib.sha1(
        input_digest(from_node, edge_type, to_node).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "ROA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── Health(결정적) ──
def health_score(metrics: dict) -> float:
    """가중 시스템 건강 점수(0~1). **STATUS ≠ APPROVAL · INSIGHT ≠ ACTION.**"""
    total = 0.0
    for key, wt in HEALTH_WEIGHTS.items():
        total += float(metrics.get(key, 0.0)) * float(wt)
    return round(total, 8)


def system_health(metrics: dict) -> str:
    """건강 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 교정 없음.**"""
    s = health_score(metrics)
    if s >= 0.7:
        return HEALTHY
    if s >= 0.4:
        return WARNING
    return DEGRADED


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
class LayerEvent:
    event_id: str
    layer_id: str
    name: str
    version: str
    prefix: str
    capabilities: list
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
class WorkflowEvent:
    event_id: str
    workflow_id: str
    name: str
    nodes: list
    edges: list
    created_from: list
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
class CrossLayerEvent:
    event_id: str
    layer: str
    event_type: str
    reference_id: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotEvent:
    event_id: str
    snapshot_id: str
    name: str
    epoch: str
    layers: list
    workflow_count: int
    event_count: int
    health_score: float
    ecosystem_hash: str
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
class DependencyEdge:
    dependency_id: str
    from_layer: str
    to_layer: str
    relation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LineageEdge:
    lineage_id: str
    from_node: str
    from_type: str
    edge_type: str
    to_node: str
    to_type: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthReport:
    health_report_id: str
    snapshot_ref: str
    metrics: dict
    health_score: float
    system_health: str              # HEALTHY | WARNING | DEGRADED (정보용)
    layer_count: int
    active_layer_count: int
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationArtifact:
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
class OrchestrationSummary:
    timestamp: str
    layer_count: int
    layer_state_distribution: dict
    workflow_count: int
    workflow_state_distribution: dict
    event_count: int
    event_type_distribution: dict
    snapshot_count: int
    dependency_count: int
    lineage_count: int
    health_report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
