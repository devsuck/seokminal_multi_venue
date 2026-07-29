"""Research Monitoring & Observability 자료형 (P23) — 관찰 전용. **동작 없음.**

연구 생태계의 건강·품질·활동·무결성을 관찰·기록만 한다. **거래·에이전트 제어·워크플로 수정·권한 변경·전략 승인·모델 배포·
자본 배분을 하지 않는다.** OBSERVE ≠ CONTROL · HEALTH ≠ APPROVAL · HEALTH ≠ DEPLOYMENT PERMISSION. 불변·append-
only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 rmon_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 모니터링 세션 생애주기(5) ──
S_CREATED = "CREATED"
S_COLLECTING = "COLLECTING"
S_ANALYZED = "ANALYZED"
S_SNAPSHOTTED = "SNAPSHOTTED"
S_ARCHIVED = "ARCHIVED"
SESSION_STATES = (S_CREATED, S_COLLECTING, S_ANALYZED, S_SNAPSHOTTED, S_ARCHIVED)
SESSION_TRANSITIONS = {
    S_CREATED: {S_COLLECTING},
    S_COLLECTING: {S_COLLECTING, S_ANALYZED},
    S_ANALYZED: {S_ANALYZED, S_SNAPSHOTTED},
    S_SNAPSHOTTED: {S_ARCHIVED, S_COLLECTING},
    S_ARCHIVED: set(),
}

# ── 건강 상태 ──
HEALTH_STATUSES = ("HEALTHY", "WARNING", "FAILED")
# ── 이상 심각도 ──
SEVERITIES = ("LOW", "MEDIUM", "HIGH")
# ── 지표 유형 ──
METRIC_TYPES = ("GAUGE", "COUNTER", "RATIO", "SCORE")
# ── 이상 규칙 ──
ANOMALY_RULES = ("MISSING_UPSTREAM_LEDGER", "BROKEN_LINEAGE", "FAILED_VERIFICATION",
                 "UNUSUAL_ACTIVITY_FREQUENCY", "REPEATED_EXPERIMENT_FAILURES",
                 "DATA_QUALITY_DEGRADATION")

# ── 아티팩트 유형 ──
ART_SESSION = "SESSION"
ART_SNAPSHOT = "SNAPSHOT"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·제어) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "PROMOTE_MODEL",
    "ACTIVATE_LIVE", "CHANGE_PERMISSION", "EXECUTE", "DEPLOY", "APPROVE", "ALLOCATE", "PROMOTE",
    "TRADE", "CONTROL_AGENT", "MODIFY_WORKFLOW",
})


class ImmutableSessionError(Exception):
    """불변 세션(중복) 위반."""


class IllegalSessionTransition(Exception):
    """유효하지 않은 세션 전이 — 차단."""


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


# ── 결정적 ID (MO* 스킴) ──
def session_id(name) -> str:
    return _id("MOC", name)


def session_event_id(sess, to, seq) -> str:
    return _id("MON", sess, to, seq)


def metric_id(name, source_reference, seq) -> str:
    return _id("MOM", name, source_reference, seq)


def health_id(component, seq) -> str:
    return _id("MOH", component, seq)


def observation_id(source, event_type, seq) -> str:
    return _id("MOO", source, event_type, seq)


def activity_event_id(source_layer, activity_type, seq) -> str:
    return _id("MOV", source_layer, activity_type, seq)


def anomaly_id(rule, source_reference, seq) -> str:
    return _id("MOA", rule, source_reference, seq)


def snapshot_id(scope, created_at) -> str:
    return _id("MOS", scope, created_at)


def report_id(scope, created_at) -> str:
    return _id("MOR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("MOF", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_session_transition(frm, to) -> bool:
    return to in SESSION_TRANSITIONS.get(frm, set())


def classify_health(score) -> str:
    """건강 점수(0..1) → 상태(결정적, 관찰용). 범위 밖은 WARNING."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "WARNING"
    if s < 0.0 or s > 1.0:
        return "WARNING"
    if s >= 0.8:
        return "HEALTHY"
    if s >= 0.5:
        return "WARNING"
    return "FAILED"


def aggregate_health(components) -> dict:
    """구성요소 건강 점수 집계(평균) → 전체 상태. components: {name: score}. 관찰만."""
    if not components:
        return {"score": 0.0, "status": "WARNING", "components": {}}
    avg = round(sum(float(v) for v in components.values()) / len(components), 6)
    return {"score": avg, "status": classify_health(avg),
            "components": dict(sorted(components.items()))}


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
    name: str
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
class MonitoringMetricRecord:
    metric_id: str
    metric_name: str
    metric_type: str
    source_layer: str
    source_reference: str
    value: float
    hash: str
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthCheckRecord:
    health_id: str
    component: str
    status: str
    metrics: dict
    score: float
    checked_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservationRecord:
    observation_id: str
    source: str
    event_type: str
    metadata: dict
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ActivityEventRecord:
    activity_event_id: str
    source_layer: str
    activity_type: str
    count: int
    detail: str
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AnomalyRecord:
    anomaly_id: str
    rule: str
    source_reference: str
    severity: str
    description: str
    is_actionable: bool  # 항상 False — 탐지·기록만, 자동 조치 없음
    detected_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    scope: str
    metrics_hash: str
    system_state_hash: str
    metric_count: int
    health_count: int
    anomaly_count: int
    observation_count: int
    is_binding: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservabilityReportRecord:
    report_id: str
    scope: str
    overall_health: str
    health_score: float
    metric_count: int
    health_check_count: int
    anomaly_count: int
    anomaly_severity_distribution: dict
    activity_count: int
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
class MonitoringSummary:
    timestamp: str
    session_event_count: int
    metric_count: int
    health_check_count: int
    observation_count: int
    activity_count: int
    anomaly_count: int
    snapshot_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
