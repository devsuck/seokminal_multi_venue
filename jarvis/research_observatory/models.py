"""Research Observatory & Control Plane 자료형 (P10.10) — 전 연구 계층 관찰·집계·시각화 전용.

P10.2~P10.9 연구 계층을 **READ ONLY** 로 소비해 스냅샷·교차계층 지표·의존 그래프·타임라인·트렌드·
대시보드·리포트를 집계한다. **관측 계층이다.** Strategy 선택·Model 승인·Trading 승인·Live 실행·
Deployment·permission·config 변경 없음. OBSERVED ≠ APPROVED · OBSERVED ≠ DEPLOYED ·
OBSERVED ≠ EXECUTED. 불변·append-only 해시체인·결정적. 물리 원장은 ob_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Observatory 생명주기 ──
CREATED = "CREATED"
COLLECTING = "COLLECTING"
ANALYZING = "ANALYZING"
REPORTING = "REPORTING"
ARCHIVED = "ARCHIVED"

OBSERVATORY_STATES = (CREATED, COLLECTING, ANALYZING, REPORTING, ARCHIVED)
OBSERVATORY_TRANSITIONS = {
    "": {CREATED},
    CREATED: {COLLECTING},
    COLLECTING: {ANALYZING},
    ANALYZING: {REPORTING},
    REPORTING: {ARCHIVED},
    ARCHIVED: set(),
}

# ── 관측 대상 계층(READ ONLY) ──
STRATEGY = "STRATEGY"
SIGNAL = "SIGNAL"
FEATURE = "FEATURE"
DATASET = "DATASET"
EXPERIMENT = "EXPERIMENT"
PORTFOLIO = "PORTFOLIO"
KNOWLEDGE_GRAPH = "KNOWLEDGE_GRAPH"
AGENT = "AGENT"
DECISION = "DECISION"
SIMULATION = "SIMULATION"
VALIDATION = "VALIDATION"

OBSERVED_LAYERS = (STRATEGY, SIGNAL, FEATURE, DATASET, EXPERIMENT, PORTFOLIO, KNOWLEDGE_GRAPH,
                   AGENT, DECISION, SIMULATION, VALIDATION)

# ── 계층 간 정방향 의존 흐름(레벨 그래프) ──
DEPENDENCY_FLOW = (
    (DATASET, FEATURE),
    (FEATURE, SIGNAL),
    (SIGNAL, STRATEGY),
    (STRATEGY, EXPERIMENT),
    (EXPERIMENT, PORTFOLIO),
    (PORTFOLIO, VALIDATION),
    (VALIDATION, SIMULATION),
)

# ── Timeline 이벤트 유형 ──
EV_STRATEGY_CREATED = "STRATEGY_CREATED"
EV_SIGNAL_CREATED = "SIGNAL_CREATED"
EV_EXPERIMENT_STARTED = "EXPERIMENT_STARTED"
EV_PORTFOLIO_CREATED = "PORTFOLIO_CREATED"
EV_VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
EV_SIMULATION_FINISHED = "SIMULATION_FINISHED"
EV_DECISION_GENERATED = "DECISION_GENERATED"

# ── Trend 방향 라벨(서술 — 자동 의사결정 아님) ──
TREND_UP = "UP"
TREND_DOWN = "DOWN"
TREND_FLAT = "FLAT"
TREND_BASELINE = "BASELINE"

# ── Artifact 유형(계보) ──
ART_SNAPSHOT = "SNAPSHOT"
ART_METRICS = "METRICS"
ART_DEPENDENCY = "DEPENDENCY"
ART_TIMELINE = "TIMELINE"
ART_TREND = "TREND"
ART_DASHBOARD = "DASHBOARD"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 관측 생명주기 전이."""


class ImmutableSnapshotError(Exception):
    """불변 스냅샷 위반(동일 snapshot_id 내용 상이)."""


class UnknownSnapshot(Exception):
    """미등록 스냅샷 참조."""


def can_transition(frm: str, to: str) -> bool:
    return to in OBSERVATORY_TRANSITIONS.get(frm, set())


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


def metrics_hash(metrics: dict) -> str:
    return _digest(dict(metrics or {}))


# ── 결정적 ID ──
def snapshot_id(name: str, epoch: str) -> str:
    return "OBS:" + hashlib.sha1(input_digest(name, epoch).encode()).hexdigest()[:12]


def snapshot_event_id(sid: str, frm: str, to: str) -> str:
    return "OBE:" + hashlib.sha1(input_digest(sid, frm, to).encode()).hexdigest()[:12]


def metric_id(snapshot_id_: str, layer: str, metric_name: str) -> str:
    return "OBM:" + hashlib.sha1(
        input_digest(snapshot_id_, layer, metric_name).encode()).hexdigest()[:12]


def dependency_id(snapshot_id_: str, from_layer: str, to_layer: str) -> str:
    return "OBD:" + hashlib.sha1(
        input_digest(snapshot_id_, from_layer, to_layer).encode()).hexdigest()[:12]


def timeline_id(snapshot_id_: str, layer: str, event_type: str, ref: str) -> str:
    return "OBT:" + hashlib.sha1(
        input_digest(snapshot_id_, layer, event_type, ref).encode()).hexdigest()[:12]


def trend_id(snapshot_id_: str, name: str) -> str:
    return "OBR:" + hashlib.sha1(input_digest(snapshot_id_, name).encode()).hexdigest()[:12]


def dashboard_id(snapshot_id_: str) -> str:
    return "OBH:" + hashlib.sha1(input_digest(snapshot_id_).encode()).hexdigest()[:12]


def report_id(snapshot_id_: str) -> str:
    return "OBP:" + hashlib.sha1(input_digest(snapshot_id_).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "OBA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 집계 헬퍼(결정적) ──
def ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) < _EPS:
        return 0.0
    return round(float(numerator) / float(denominator), 8)


def graph_density(nodes: int, edges: int) -> float:
    """방향 그래프 밀도 edges / (nodes*(nodes-1)). 관측 지표."""
    n = int(nodes)
    if n < 2:
        return 0.0
    return round(float(edges) / (n * (n - 1)), 8)


def trend_direction(current: float, previous: float | None) -> str:
    if previous is None:
        return TREND_BASELINE
    d = float(current) - float(previous)
    if d > _EPS:
        return TREND_UP
    if d < -_EPS:
        return TREND_DOWN
    return TREND_FLAT


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
class SnapshotEvent:
    """관측 스냅샷 등록·상태 전이 이벤트(이벤트 소싱). 정체성 불변."""
    event_id: str
    snapshot_id: str
    name: str
    epoch: str
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
class ObservatoryMetric:
    metric_id: str
    snapshot_id: str
    layer: str
    metric_name: str
    value: float
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyEdge:
    dependency_id: str
    snapshot_id: str
    from_layer: str
    to_layer: str
    from_count: int
    to_count: int
    broken: bool                    # to 존재하나 from 부재 → broken dependency
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TimelineEvent:
    timeline_id: str
    snapshot_id: str
    layer: str
    event_type: str
    reference: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrendReport:
    trend_id: str
    snapshot_id: str
    name: str
    value: float
    previous_value: float
    direction: str                  # UP | DOWN | FLAT | BASELINE (서술 — 의사결정 아님)
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Dashboard:
    dashboard_id: str
    snapshot_id: str
    metrics: dict                   # 집계 관찰 정보만
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservatoryReport:
    report_id: str
    snapshot_id: str
    name: str
    metric_count: int
    dependency_count: int
    broken_dependency_count: int
    timeline_count: int
    trend_count: int
    dashboard_metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservatoryArtifact:
    artifact_id: str
    artifact_type: str
    ref_id: str
    parent_artifact: str
    snapshot_id: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservatorySummary:
    timestamp: str
    snapshot_count: int
    snapshot_state_distribution: dict
    metric_count: int
    dependency_count: int
    broken_dependency_count: int
    timeline_count: int
    trend_count: int
    dashboard_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
