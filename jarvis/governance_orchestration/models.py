"""Research Governance Orchestration 자료형 (P10.23) — 전 거버넌스 계층 관찰·집계 최상위 조정. 읽기전용.

P9.8~P10.22 전 거버넌스·연구 인텔리전스 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 계층 레지스트리·
시스템 상태 스냅샷·거버넌스 건강 요약·의존 지도·교차계층 충돌 기록·오케스트레이션 리포트·연구 OS 상태를
제공한다. **실행 계층 아님 — 거래·주문·portfolio 수정·capital 배분·strategy 배포·permission/config 변경 없음.**
ORCHESTRATION ≠ EXECUTION · MONITORING ≠ CONTROL · STATUS ≠ APPROVAL · AGGREGATION ≠ ACTION. 불변·append-only
해시체인·결정적. 물리 원장은 go_ 접두사(Governance Orchestration). (research_orchestration/or_ 는 P10.17 소유.)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── Layer 생명주기 ──
REGISTERED = "REGISTERED"
CONNECTED = "CONNECTED"
MONITORED = "MONITORED"
ARCHIVED = "ARCHIVED"
LAYER_STATES = (REGISTERED, CONNECTED, MONITORED, ARCHIVED)
LAYER_TRANSITIONS = {
    "": {REGISTERED},
    REGISTERED: {CONNECTED, ARCHIVED},
    CONNECTED: {MONITORED, ARCHIVED},
    MONITORED: {ARCHIVED},
    ARCHIVED: set(),
}

# ── Snapshot 생명주기 ──
CREATED = "CREATED"
GENERATED = "GENERATED"
VERIFIED = "VERIFIED"
SNAPSHOT_STATES = (CREATED, GENERATED, VERIFIED)
SNAPSHOT_TRANSITIONS = {
    "": {CREATED},
    CREATED: {GENERATED},
    GENERATED: {VERIFIED},
    VERIFIED: set(),
}

# ── 상태 라벨(계층 보고) ──
STATUS_LABELS = ("HEALTHY", "WARNING", "DEGRADED", "UNKNOWN")

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

# ── 교차계층 충돌 범주 ──
CF_DEPENDENCY_CYCLE = "dependency_cycle"
CF_VERSION_MISMATCH = "version_mismatch"
CF_STATE_INCONSISTENCY = "state_inconsistency"
CF_DUPLICATE_OWNERSHIP = "duplicate_ownership"
CF_MISSING_DEPENDENCY = "missing_dependency"
CONFLICT_CATEGORIES = (CF_DEPENDENCY_CYCLE, CF_VERSION_MISMATCH, CF_STATE_INCONSISTENCY,
                       CF_DUPLICATE_OWNERSHIP, CF_MISSING_DEPENDENCY)

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_STATUS = "STATUS"
NODE_SNAPSHOT = "SNAPSHOT"
NODE_HEALTH = "HEALTH"
NODE_CONFLICT = "CONFLICT"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_STATUS, NODE_SNAPSHOT, NODE_HEALTH, NODE_CONFLICT, NODE_REPORT)

# ── 거버넌스 건강 점수 가중치(합=1.0) — 정보용, 집행 아님 ──
HEALTH_WEIGHTS = {
    "layer_availability": 0.25,
    "monitoring_coverage": 0.20,
    "dependency_integrity": 0.20,
    "conflict_freedom": 0.20,
    "status_freshness": 0.15,
}

# ── System health 라벨 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_STATUS = "STATUS"
ART_SNAPSHOT = "SNAPSHOT"
ART_HEALTH = "HEALTH"
ART_DEPENDENCY = "DEPENDENCY"
ART_CONFLICT = "CONFLICT"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableLayerError(Exception):
    """불변 레이어 위반."""


class ImmutableStatusError(Exception):
    """불변 상태 기록 위반."""


class UnknownLayer(Exception):
    """미등록 레이어 참조."""


class UnknownSnapshot(Exception):
    """미등록 스냅샷 참조."""


class InvalidConflictCategory(Exception):
    """미등록 충돌 범주."""


class InvalidDependencyGraph(Exception):
    """유효하지 않은 의존 그래프(미등록 노드/자기참조/순환)."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_layer(frm: str, to: str) -> bool:
    return _can(LAYER_TRANSITIONS, frm, to)


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


def system_hash(layers: list, health_score: float, conflict_count: int) -> str:
    return _digest({"layers": sorted(layers or []), "health": round(float(health_score), 8),
                    "conflicts": int(conflict_count)})


# ── 결정적 ID ──
def layer_id(name: str) -> str:
    return "GOL:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def layer_event_id(lid: str, frm: str, to: str) -> str:
    return "GLE:" + hashlib.sha1(input_digest(lid, frm, to).encode()).hexdigest()[:12]


def status_id(layer_reference: str, epoch: str) -> str:
    return "GOT:" + hashlib.sha1(
        input_digest(layer_reference, epoch).encode()).hexdigest()[:12]


def snapshot_id(name: str, epoch: str) -> str:
    return "GOS:" + hashlib.sha1(input_digest(name, epoch).encode()).hexdigest()[:12]


def snapshot_event_id(sid: str, frm: str, to: str) -> str:
    return "GSE:" + hashlib.sha1(input_digest(sid, frm, to).encode()).hexdigest()[:12]


def health_id(scope: str, epoch: str) -> str:
    return "GOH:" + hashlib.sha1(input_digest(scope, epoch).encode()).hexdigest()[:12]


def dependency_id(from_layer: str, to_layer: str) -> str:
    return "GOD:" + hashlib.sha1(input_digest(from_layer, to_layer).encode()).hexdigest()[:12]


def conflict_id(layer_a: str, layer_b: str, category: str) -> str:
    return "GOC:" + hashlib.sha1(
        input_digest(layer_a, layer_b, category).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "GOR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "GOA:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수/평가(결정적, 정보용) ──
def severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.0)


def health_score(metrics: dict) -> float:
    """가중 거버넌스 건강 점수(0~1). **AGGREGATION ≠ ACTION — 집행/승인 신호 아님.**"""
    total = 0.0
    for key, wt in HEALTH_WEIGHTS.items():
        total += float((metrics or {}).get(key, 0.0)) * float(wt)
    return round(total, 8)


def system_health(metrics: dict) -> str:
    """건강 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 조치/집행 없음.**"""
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
    layer_type: str
    source_prefix: str
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
class LayerStatusRecord:
    status_id: str
    layer_reference: str
    status: str
    metrics: dict
    metrics_hash: str
    epoch: str
    timestamp: str
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
class SystemSnapshotEvent:
    event_id: str
    snapshot_id: str
    name: str
    epoch: str
    layers: list
    layer_count: int
    health_score: float
    conflict_count: int
    system_hash: str
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
class HealthSummary:
    health_id: str
    scope: str
    epoch: str
    layer_count: int
    monitored_layer_count: int
    metrics: dict
    health_score: float
    system_health: str
    conflict_count: int
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConflictRecord:
    conflict_id: str
    layer_a: str
    layer_b: str
    category: str
    severity: str
    detail: str
    evidence: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationReport:
    report_id: str
    scope: str
    layer_count: int
    layer_state_distribution: dict
    status_count: int
    status_label_distribution: dict
    dependency_count: int
    snapshot_count: int
    conflict_count: int
    conflict_category_distribution: dict
    metrics: dict
    health_score: float
    system_health: str
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
    status_count: int
    dependency_count: int
    snapshot_count: int
    health_summary_count: int
    conflict_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
