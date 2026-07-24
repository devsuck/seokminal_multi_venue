"""Autonomous Research Control Plane 자료형 (P12.10) — 관찰·분석·기록 전용.

연구 시스템 상태·헬스·이벤트·지표·이상(anomaly)·리포트를 **관찰·기록**만 한다. **자동 복구·배포·결정을 하지 않는다.**
OBSERVE ≠ EXECUTION · MONITOR ≠ CONTROL · ANOMALY ≠ RECOVERY. 불변·append-only·SHA256 해시체인·이벤트 소싱·
결정적. 물리 원장은 rctl_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 상태 레지스트리 생애주기(5) ──
S_INITIALIZED = "INITIALIZED"
S_OBSERVED = "OBSERVED"
S_ANALYZED = "ANALYZED"
S_REPORTED = "REPORTED"
S_ARCHIVED = "ARCHIVED"
CONTROL_STATES = (S_INITIALIZED, S_OBSERVED, S_ANALYZED, S_REPORTED, S_ARCHIVED)

ALLOWED_TRANSITIONS = {
    S_INITIALIZED: {S_OBSERVED},
    S_OBSERVED: {S_OBSERVED, S_ANALYZED},
    S_ANALYZED: {S_ANALYZED, S_REPORTED, S_OBSERVED},
    S_REPORTED: {S_ARCHIVED, S_OBSERVED},
    S_ARCHIVED: set(),
}

# ── 헬스 상태(필드) ──
HEALTH_LEVELS = ("HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN")

# ── 이상 심각도 ──
SEVERITIES = ("INFO", "WARNING", "CRITICAL")

# ── 아티팩트(계보) 유형 ──
ART_STATE = "STATE"
ART_SNAPSHOT = "SNAPSHOT"

# ── 금지(실행·거래·배포·복구) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "AUTO_RECOVER", "AUTO_DEPLOY", "AUTO_DECIDE", "EXECUTE_TRADE", "PLACE_ORDER", "RUN_ORDER",
    "START_TRADING", "DEPLOY_MODEL", "DEPLOY", "ALLOCATE_CAPITAL", "PROMOTE_MODEL",
    "CHANGE_PERMISSION", "RESTART_SYSTEM", "ROLLBACK", "REMEDIATE",
})


class ImmutableStateError(Exception):
    """불변 상태 레지스트리(중복) 위반."""


class IllegalControlTransition(Exception):
    """유효하지 않은 상태 전이 — 거부."""


class UnknownStateError(Exception):
    """미등록 상태 레지스트리 참조."""


class ForbiddenControlActionError(Exception):
    """금지된 제어/복구/배포 동작 시도 — 차단."""


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


# ── 결정적 ID (CT* 스킴) ──
def state_id(name: str) -> str:
    return "CTS:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def state_event_id(state: str, to_state: str, seq: int) -> str:
    return "CTL:" + hashlib.sha1(input_digest(state, to_state, seq).encode()).hexdigest()[:12]


def event_id(state: str, kind: str, seq: int) -> str:
    return "CTE:" + hashlib.sha1(input_digest(state, kind, seq).encode()).hexdigest()[:12]


def health_id(state: str, seq: int) -> str:
    return "CTH:" + hashlib.sha1(input_digest(state, seq).encode()).hexdigest()[:12]


def metric_id(state: str, key: str, seq: int) -> str:
    return "CTM:" + hashlib.sha1(input_digest(state, key, seq).encode()).hexdigest()[:12]


def alert_id(state: str, code: str, seq: int) -> str:
    return "CTA:" + hashlib.sha1(input_digest(state, code, seq).encode()).hexdigest()[:12]


def report_id(state: str, scope: str, generated_at: str) -> str:
    return "CTR:" + hashlib.sha1(input_digest(state, scope, generated_at).encode()).hexdigest()[:12]


def artifact_id(artifact_type: str, ref_id: str) -> str:
    return "CTF:" + hashlib.sha1(input_digest(artifact_type, ref_id).encode()).hexdigest()[:12]


def snapshot_id(generated_at: str) -> str:
    return "CTN:" + hashlib.sha1(input_digest("SNAPSHOT", generated_at).encode()).hexdigest()[:12]


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def classify_health(score: float) -> str:
    """헬스 점수(0..1) → 등급. 결정적, 관찰 라벨만(제어 아님)."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if s < 0.0 or s > 1.0:
        return "UNKNOWN"
    if s >= 0.8:
        return "HEALTHY"
    if s >= 0.5:
        return "DEGRADED"
    return "CRITICAL"


def severity_for(health_level: str) -> str:
    """헬스 등급 → 이상 심각도(결정적 매핑). 기록용 라벨만."""
    return {"CRITICAL": "CRITICAL", "DEGRADED": "WARNING"}.get(health_level, "INFO")


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
class StateEventRecord:
    state_event_id: str
    state_id: str
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
class ResearchEventRecord:
    event_id: str
    state_id: str
    kind: str
    source_layer: str
    source_ref: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthRecord:
    health_id: str
    state_id: str
    score: float
    level: str
    note: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetricRecord:
    metric_id: str
    state_id: str
    key: str
    value: float
    unit: str
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    state_id: str
    code: str
    severity: str
    detail: str
    is_actionable: bool  # 항상 False — 기록 전용, 자동 복구 없음
    recorded_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SystemReportRecord:
    report_id: str
    state_id: str
    scope: str
    event_count: int
    health_count: int
    metric_count: int
    alert_count: int
    latest_health: str
    state_status: str
    severity_distribution: dict
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
class SnapshotRecord:
    snapshot_id: str
    timestamp: str
    state_count: int
    state_event_count: int
    event_count: int
    health_count: int
    metric_count: int
    alert_count: int
    report_count: int
    artifact_count: int
    state_distribution: dict
    is_binding: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ControlSummary:
    timestamp: str
    state_event_count: int
    event_count: int
    health_count: int
    metric_count: int
    alert_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
