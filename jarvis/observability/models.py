"""Observability & Operations Intelligence 자료형 (P17) — 모니터·측정·분석·보고 전용. **동작 실행 없음.**

시스템 건강·연구 파이프라인·성능·데이터 품질·감사 가시성을 관찰·기록만 한다. **거래·주문·배포·자동 복구·자동 결정·자동
승인을 하지 않는다.** OBSERVE ≠ EXECUTE · MONITOR ≠ CONTROL · ALERT ≠ REMEDIATION. 불변·append-only·SHA256
해시체인·이벤트 소싱·결정적. 물리 원장은 obs_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 건강 상태(6) ──
H_UNKNOWN = "UNKNOWN"
H_HEALTHY = "HEALTHY"
H_WARNING = "WARNING"
H_DEGRADED = "DEGRADED"
H_FAILED = "FAILED"
H_RECOVERED = "RECOVERED"
HEALTH_STATES = (H_UNKNOWN, H_HEALTHY, H_WARNING, H_DEGRADED, H_FAILED, H_RECOVERED)

# FAILED 는 RECOVERED 를 거쳐야 HEALTHY 로 갈 수 있다(직접 FAILED→HEALTHY 금지).
ALLOWED_TRANSITIONS = {
    H_UNKNOWN: {H_HEALTHY, H_WARNING, H_DEGRADED, H_FAILED},
    H_HEALTHY: {H_HEALTHY, H_WARNING, H_DEGRADED, H_FAILED},
    H_WARNING: {H_WARNING, H_HEALTHY, H_DEGRADED, H_FAILED},
    H_DEGRADED: {H_DEGRADED, H_WARNING, H_HEALTHY, H_FAILED, H_RECOVERED},
    H_FAILED: {H_FAILED, H_RECOVERED, H_DEGRADED},
    H_RECOVERED: {H_RECOVERED, H_HEALTHY, H_WARNING, H_DEGRADED, H_FAILED},
}

# ── 알림 유형·심각도 ──
ALERT_TYPES = ("INTEGRITY_FAILURE", "BROKEN_LINEAGE", "SECURITY_ISSUE", "DATA_QUALITY_ISSUE",
               "PIPELINE_FAILURE", "PERFORMANCE_DEGRADATION")
SEVERITIES = ("INFO", "WARNING", "CRITICAL")

# ── 데이터 품질 이슈 코드 ──
QUALITY_CODES = ("MISSING_DATA", "STALE_DATA", "SCHEMA_MISMATCH", "BROKEN_LINEAGE",
                 "DUPLICATE_ARTIFACT", "INVALID_REFERENCE", "INTEGRITY_FAILURE")

# ── 아티팩트 유형 ──
ART_TARGET = "TARGET"
ART_DASHBOARD = "DASHBOARD"

# ── 절대 금지(실행·자동조치) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE", "TRADE", "PLACE_ORDER", "RUN_ORDER", "DEPLOY", "DEPLOY_MODEL", "ALLOCATE_CAPITAL",
    "PROMOTE_MODEL", "CHANGE_PERMISSION", "GRANT_PERMISSION", "AUTO_RECOVER", "AUTO_RESTART",
    "AUTO_DEPLOY", "AUTO_DECIDE", "AUTO_APPROVE", "REMEDIATE", "ROLLBACK",
})


class ImmutableTargetError(Exception):
    """불변 모니터 대상(중복) 위반."""


class IllegalHealthTransition(Exception):
    """유효하지 않은 건강 상태 전이 — 차단."""


class UnknownTargetError(Exception):
    """미등록 모니터 대상 참조."""


class ForbiddenObservabilityAction(Exception):
    """금지된 실행/자동조치 시도 — 차단."""


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


# ── 결정적 ID (OI* 스킴) ──
def target_id(name: str) -> str:
    return "OIU:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def health_event_id(target: str, to_state: str, seq: int) -> str:
    return "OIH:" + hashlib.sha1(input_digest(target, to_state, seq).encode()).hexdigest()[:12]


def metric_id(key: str, target: str, seq: int) -> str:
    return "OIM:" + hashlib.sha1(input_digest(key, target, seq).encode()).hexdigest()[:12]


def observation_id(code: str, subject: str, seq: int) -> str:
    return "OIO:" + hashlib.sha1(input_digest(code, subject, seq).encode()).hexdigest()[:12]


def alert_id(atype: str, subject: str, seq: int) -> str:
    return "OIA:" + hashlib.sha1(input_digest(atype, subject, seq).encode()).hexdigest()[:12]


def perf_id(name: str, seq: int) -> str:
    return "OIP:" + hashlib.sha1(input_digest(name, seq).encode()).hexdigest()[:12]


def availability_id(target: str, seq: int) -> str:
    return "OIV:" + hashlib.sha1(input_digest(target, seq).encode()).hexdigest()[:12]


def audit_obs_id(subject: str, seq: int) -> str:
    return "OID:" + hashlib.sha1(input_digest(subject, seq).encode()).hexdigest()[:12]


def artifact_id(atype: str, ref: str) -> str:
    return "OIF:" + hashlib.sha1(input_digest(atype, ref).encode()).hexdigest()[:12]


def dashboard_id(kind: str, generated_at: str) -> str:
    return "OIN:" + hashlib.sha1(input_digest(kind, generated_at).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def classify_health(score: float) -> str:
    """건강 점수(0..1) → 상태 라벨(결정적, 관찰용). 범위 밖은 UNKNOWN."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return H_UNKNOWN
    if s < 0.0 or s > 1.0:
        return H_UNKNOWN
    if s >= 0.9:
        return H_HEALTHY
    if s >= 0.7:
        return H_WARNING
    if s >= 0.4:
        return H_DEGRADED
    return H_FAILED


def severity_for_health(state: str) -> str:
    return {"FAILED": "CRITICAL", "DEGRADED": "CRITICAL", "WARNING": "WARNING"}.get(state, "INFO")


def detect_cycle_check(edges: list) -> bool:
    """방향 그래프 순환 존재 여부(DFS, 결정적). 계보 검증용."""
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
class HealthEventRecord:
    health_event_id: str
    target_id: str
    name: str
    kind: str
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
class MetricRecord:
    metric_id: str
    key: str
    target_id: str
    value: float
    unit: str
    metadata: dict
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservationRecord:
    observation_id: str
    code: str
    subject: str
    detail: str
    metadata: dict
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    alert_type: str
    severity: str
    subject: str
    detail: str
    is_actionable: bool  # 항상 False — 기록 전용, 자동 조치 없음
    metadata: dict
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PerfSnapshotRecord:
    perf_id: str
    name: str
    duration: float
    unit: str
    metadata: dict
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AvailabilityRecord:
    availability_id: str
    target_id: str
    available: bool
    detail: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditObservationRecord:
    audit_obs_id: str
    subject: str
    observation: str
    metadata: dict
    recorded_at: str
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
class DashboardRecord:
    dashboard_id: str
    kind: str
    payload: dict
    is_binding: bool
    generated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ObservabilitySummary:
    timestamp: str
    health_event_count: int
    metric_count: int
    observation_count: int
    alert_count: int
    perf_count: int
    availability_count: int
    audit_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
