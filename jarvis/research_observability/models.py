"""Research Monitoring & Observability 자료형 (P10.18) — 연구 시스템 건강 관찰 전용.

P9.8~P10.17 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구 건강 레지스트리·지표 레지스트리·
모니터링 스냅샷·이상 관찰 레지스트리·품질 신호 이력·연구 활동 타임라인·관측 리포트·모니터링 계보를 제공한다.
**복구 실행·연구 객체 수정·strategy 변경·parameter 수정·workflow 재시작·배포 없음.** OBSERVATION ≠ ACTION ·
DETECTION ≠ CORRECTION · WARNING ≠ INTERVENTION · MONITORING ≠ EXECUTION. 불변·append-only 해시체인·결정적.
물리 원장은 mh_ 접두사(Monitoring Health Intelligence).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"
_EPS = 1e-9

# ── 건강 상태 ──
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"
UNKNOWN = "UNKNOWN"
HEALTH_STATES = (HEALTHY, WARNING, DEGRADED, UNKNOWN)

# ── 지표 유형 ──
M_RESEARCH_VOLUME = "research_volume"
M_VALIDATION_RATE = "validation_rate"
M_FAILURE_RATE = "failure_rate"
M_REPRODUCIBILITY_SCORE = "reproducibility_score"
M_DATA_QUALITY_SCORE = "data_quality_score"
M_WORKFLOW_HEALTH = "workflow_health"
METRIC_TYPES = (M_RESEARCH_VOLUME, M_VALIDATION_RATE, M_FAILURE_RATE, M_REPRODUCIBILITY_SCORE,
                M_DATA_QUALITY_SCORE, M_WORKFLOW_HEALTH)

# ── 이상(anomaly) 범주 ──
A_SUDDEN_QUALITY_DROP = "sudden_quality_drop"
A_REPEATED_FAILURE = "repeated_failure"
A_ABNORMAL_ACTIVITY = "abnormal_activity"
A_MISSING_DATA = "missing_data"
A_INCONSISTENT_RESULT = "inconsistent_result"
ANOMALY_CATEGORIES = (A_SUDDEN_QUALITY_DROP, A_REPEATED_FAILURE, A_ABNORMAL_ACTIVITY,
                      A_MISSING_DATA, A_INCONSISTENT_RESULT)

# ── 이상 생명주기(관찰 상태 추적 — 조치 아님) ──
OBSERVED = "OBSERVED"
ACKNOWLEDGED = "ACKNOWLEDGED"
CLEARED = "CLEARED"
ARCHIVED = "ARCHIVED"
ANOMALY_STATES = (OBSERVED, ACKNOWLEDGED, CLEARED, ARCHIVED)
ANOMALY_TRANSITIONS = {
    "": {OBSERVED},
    OBSERVED: {ACKNOWLEDGED, CLEARED, ARCHIVED},
    ACKNOWLEDGED: {CLEARED, ARCHIVED},
    CLEARED: {ARCHIVED},
    ARCHIVED: set(),
}

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 1.0}

# ── 활동 이벤트 유형(예시) ──
ACT_METRIC_RECORDED = "METRIC_RECORDED"
ACT_HEALTH_RECORDED = "HEALTH_RECORDED"
ACT_SNAPSHOT_TAKEN = "SNAPSHOT_TAKEN"
ACT_ANOMALY_OBSERVED = "ANOMALY_OBSERVED"
ACT_QUALITY_SAMPLED = "QUALITY_SAMPLED"
ACTIVITY_TYPES = (ACT_METRIC_RECORDED, ACT_HEALTH_RECORDED, ACT_SNAPSHOT_TAKEN,
                  ACT_ANOMALY_OBSERVED, ACT_QUALITY_SAMPLED)

# ── 계보 노드 유형 ──
NODE_LAYER = "LAYER"
NODE_METRIC = "METRIC"
NODE_OBSERVATION = "OBSERVATION"
NODE_SNAPSHOT = "SNAPSHOT"
NODE_REPORT = "REPORT"
NODE_TYPES = (NODE_LAYER, NODE_METRIC, NODE_OBSERVATION, NODE_SNAPSHOT, NODE_REPORT)

# ── 건강 점수 가중치(합=1.0) — 정보용, 실행/조치 아님 ──
HEALTH_WEIGHTS = {
    "validation_rate": 0.25,
    "reproducibility_score": 0.25,
    "data_quality_score": 0.20,
    "workflow_health": 0.20,
    "failure_rate_inverse": 0.10,
}

# ── Artifact 유형(계보) ──
ART_LAYER = "LAYER"
ART_METRIC = "METRIC"
ART_HEALTH = "HEALTH"
ART_SNAPSHOT = "SNAPSHOT"
ART_ANOMALY = "ANOMALY"
ART_ACTIVITY = "ACTIVITY"
ART_QUALITY = "QUALITY"
ART_REPORT = "REPORT"


class IllegalTransition(Exception):
    """차단된 생명주기 전이."""


class ImmutableHealthError(Exception):
    """불변 건강 기록 위반."""


class ImmutableMetricError(Exception):
    """불변 지표 기록 위반."""


class ImmutableAnomalyError(Exception):
    """불변 이상 기록 위반."""


class UnknownAnomaly(Exception):
    """미등록 이상 참조."""


class UnknownSnapshot(Exception):
    """미등록 스냅샷 참조."""


class InvalidHealthStatus(Exception):
    """미등록 건강 상태."""


class InvalidMetricType(Exception):
    """미등록 지표 유형."""


class InvalidAnomalyCategory(Exception):
    """미등록 이상 범주."""


def _can(table: dict, frm: str, to: str) -> bool:
    return to in table.get(frm, set())


def can_transition_anomaly(frm: str, to: str) -> bool:
    return _can(ANOMALY_TRANSITIONS, frm, to)


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


def snapshot_hash(collected_metrics: list, health_summary: dict) -> str:
    return _digest({"metrics": sorted(collected_metrics or []),
                    "health": dict(health_summary or {})})


# ── 결정적 ID ──
def health_id(source_layer: str, epoch: str) -> str:
    return "MHH:" + hashlib.sha1(input_digest(source_layer, epoch).encode()).hexdigest()[:12]


def metric_id(metric_type: str, source_reference: str, epoch: str) -> str:
    return "MHM:" + hashlib.sha1(
        input_digest(metric_type, source_reference, epoch).encode()).hexdigest()[:12]


def snapshot_id(name: str, epoch: str) -> str:
    return "MHS:" + hashlib.sha1(input_digest(name, epoch).encode()).hexdigest()[:12]


def anomaly_id(source: str, category: str, epoch: str) -> str:
    return "MHA:" + hashlib.sha1(
        input_digest(source, category, epoch).encode()).hexdigest()[:12]


def anomaly_event_id(aid: str, frm: str, to: str) -> str:
    return "MAE:" + hashlib.sha1(input_digest(aid, frm, to).encode()).hexdigest()[:12]


def activity_id(scope: str, activity_type: str, reference: str) -> str:
    return "MHT:" + hashlib.sha1(
        input_digest(scope, activity_type, reference).encode()).hexdigest()[:12]


def quality_id(source_reference: str, epoch: str) -> str:
    return "MHQ:" + hashlib.sha1(
        input_digest(source_reference, epoch).encode()).hexdigest()[:12]


def report_id(scope: str) -> str:
    return "MHR:" + hashlib.sha1(input_digest(scope).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "MHX:" + hashlib.sha1(
        input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


# ── 점수(결정적, 정보용) ──
def severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.0)


def health_score(metrics: dict) -> float:
    """가중 건강 점수(0~1). **OBSERVATION ≠ ACTION — 조치/복구 신호 아님.**

    failure_rate 는 역수(1-failure_rate)로 반영한다."""
    m = dict(metrics or {})
    if "failure_rate_inverse" not in m and "failure_rate" in m:
        m["failure_rate_inverse"] = max(0.0, 1.0 - float(m.get("failure_rate", 0.0)))
    total = 0.0
    for key, wt in HEALTH_WEIGHTS.items():
        total += float(m.get(key, 0.0)) * float(wt)
    return round(total, 8)


def health_status(metrics: dict) -> str:
    """건강 지표 → HEALTHY/WARNING/DEGRADED. **정보용 — 자동 조치/복구 없음.**"""
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
class HealthRecord:
    health_id: str
    source_layer: str
    status: str
    metrics: dict
    metrics_hash: str
    health_score: float
    epoch: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetricRecord:
    metric_id: str
    metric_type: str
    value: float
    source_reference: str
    epoch: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservationSnapshot:
    snapshot_id: str
    name: str
    epoch: str
    collected_metrics: list
    health_summary: dict
    metric_count: int
    snapshot_hash: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AnomalyEvent:
    event_id: str
    anomaly_id: str
    source: str
    category: str
    severity: str
    evidence: list
    from_state: str
    to_state: str
    status: str
    epoch: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ActivityEvent:
    activity_id: str
    scope: str
    activity_type: str
    reference: str
    detail: str
    timestamp: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QualitySignal:
    quality_id: str
    source_reference: str
    metric_type: str
    value: float
    epoch: str
    interpretation: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservabilityReport:
    report_id: str
    scope: str
    health_score: float
    health_status: str
    metric_count: int
    metric_type_distribution: dict
    health_record_count: int
    health_status_distribution: dict
    snapshot_count: int
    anomaly_count: int
    anomaly_severity_distribution: dict
    anomaly_state_distribution: dict
    activity_count: int
    quality_signal_count: int
    degradation_indicators: list
    metrics: dict
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservabilityArtifact:
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
class ObservabilitySummary:
    timestamp: str
    metric_count: int
    metric_type_distribution: dict
    health_record_count: int
    health_status_distribution: dict
    snapshot_count: int
    anomaly_count: int
    anomaly_state_distribution: dict
    activity_count: int
    quality_signal_count: int
    report_count: int

    def to_dict(self) -> dict:
        return asdict(self)
