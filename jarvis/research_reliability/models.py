"""Research Self-Healing & Reliability Engineering 자료형 (P24) — 신뢰성 기록 전용. **동작 없음.**

연구 인프라 장애를 탐지·기록, 복구 계획·시도를 기록, 무결성을 검증, 신뢰성 이력을 유지, 반복 장애를 분석한다.
**이것은 실행 복구 시스템이 아니다.** 거래 시스템 재시작·프로덕션 수정·자동 배포·권한 변경·전략 실행·모델 자동 수정을
하지 않는다. RECORD ≠ REPAIR · INCIDENT ≠ EXECUTION · RECOVERY = RESEARCH-PROCESS RECOVERY(≠ LIVE SYSTEM).
불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장 rel_ 접두사. 상위 계층(P10~P23)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 장애(incident) 생애주기(5) — 이벤트 소싱 ──
I_OPEN = "OPEN"
I_ANALYZING = "ANALYZING"
I_RECOVERY_PLANNED = "RECOVERY_PLANNED"
I_RESOLVED = "RESOLVED"
I_ARCHIVED = "ARCHIVED"
INCIDENT_STATES = (I_OPEN, I_ANALYZING, I_RECOVERY_PLANNED, I_RESOLVED, I_ARCHIVED)
INCIDENT_TRANSITIONS = {
    I_OPEN: {I_ANALYZING},
    I_ANALYZING: {I_ANALYZING, I_RECOVERY_PLANNED},
    I_RECOVERY_PLANNED: {I_RECOVERY_PLANNED, I_RESOLVED, I_ANALYZING},
    I_RESOLVED: {I_ARCHIVED, I_ANALYZING},
    I_ARCHIVED: set(),
}

# ── 포스트모템(postmortem) 생애주기(3) — 이벤트 소싱, 사람 검토 필수 ──
P_DRAFT = "DRAFT"
P_REVIEWED = "REVIEWED"
P_RECORDED = "RECORDED"
POSTMORTEM_STATES = (P_DRAFT, P_REVIEWED, P_RECORDED)
POSTMORTEM_TRANSITIONS = {
    P_DRAFT: {P_REVIEWED},
    P_REVIEWED: {P_RECORDED, P_DRAFT},
    P_RECORDED: set(),
}

# ── 장애 범주 ──
INCIDENT_CATEGORIES = ("DATA_FAILURE", "LINEAGE_FAILURE", "LEDGER_FAILURE", "VALIDATION_FAILURE",
                       "PIPELINE_FAILURE", "CONFIGURATION_FAILURE")
# ── 심각도 ──
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
# ── 복구 이벤트 결과 ──
RECOVERY_RESULTS = ("RECORDED", "VERIFIED", "FAILED")
# ── 무결성 검사 유형 ──
INTEGRITY_CHECK_TYPES = ("HASH_CHECK", "LINEAGE_CHECK", "SCHEMA_CHECK", "REPLAY_CHECK")
# ── 무결성 검사 결과 ──
CHECK_RESULTS = ("PASS", "FAIL", "INCONCLUSIVE")
# ── 신뢰성 지표 이름 ──
RELIABILITY_METRICS = ("incident_frequency", "mean_resolution_time", "failed_validation_rate",
                       "ledger_integrity_score", "lineage_health_score",
                       "research_availability_score")

# ── 아티팩트 유형 ──
ART_INCIDENT = "INCIDENT"
ART_PLAN = "RECOVERY_PLAN"
ART_POSTMORTEM = "POSTMORTEM"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·수정·복구실행) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "CHANGE_PERMISSION", "MODIFY_MODEL", "REPAIR_LIVE", "RESTART_EXECUTION", "EXECUTE", "DEPLOY",
    "ALLOCATE", "REPAIR", "RESTART", "PROMOTE", "TRADE", "MODIFY_CONFIGURATION",
})


class ImmutableIncidentError(Exception):
    """불변 장애(중복 genesis) 위반."""


class IllegalIncidentTransition(Exception):
    """유효하지 않은 장애 전이 — 차단."""


class IllegalPostmortemTransition(Exception):
    """유효하지 않은 포스트모템 전이 — 차단."""


class ReviewerRequired(Exception):
    """포스트모템 RECORDED 는 사람 검토(reviewer) 필수 — 자동 확정 금지."""


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


# ── 결정적 ID (RL* 스킴) ──
def incident_id(source_layer, category, description) -> str:
    return _id("RLI", source_layer, category, description)


def incident_event_id(inc, to, seq) -> str:
    return _id("RLN", inc, to, seq)


def plan_id(inc, seq) -> str:
    return _id("RLP", inc, seq)


def recovery_event_id(inc, action, seq) -> str:
    return _id("RLE", inc, action, seq)


def integrity_check_id(target_layer, check_type, seq) -> str:
    return _id("RLC", target_layer, check_type, seq)


def reliability_metric_id(metric_name, seq) -> str:
    return _id("RLM", metric_name, seq)


def postmortem_id(inc) -> str:
    return _id("RLO", inc)


def postmortem_event_id(pm, to, seq) -> str:
    return _id("RLD", pm, to, seq)


def report_id(scope, created_at) -> str:
    return _id("RLR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("RLA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_incident_transition(frm, to) -> bool:
    return to in INCIDENT_TRANSITIONS.get(frm, set())


def can_postmortem_transition(frm, to) -> bool:
    return to in POSTMORTEM_TRANSITIONS.get(frm, set())


def classify_availability(score) -> str:
    """가용성 점수(0..1) → 라벨(결정적, 관찰용). 범위 밖은 DEGRADED."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "DEGRADED"
    if s < 0.0 or s > 1.0:
        return "DEGRADED"
    if s >= 0.9:
        return "AVAILABLE"
    if s >= 0.6:
        return "DEGRADED"
    return "UNAVAILABLE"


def ratio(numerator, denominator) -> float:
    """결정적 비율(분모 0 → 0.0)."""
    d = float(denominator)
    if d == 0.0:
        return 0.0
    return round(float(numerator) / d, 6)


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
class IncidentEventRecord:
    incident_event_id: str
    incident_id: str
    source_layer: str
    severity: str
    category: str
    description: str
    from_state: str
    to_state: str
    note: str
    detected_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryPlanRecord:
    plan_id: str
    incident_id: str
    steps: list
    owner: str
    auto_execute: bool  # 항상 False — 자동 실행 없음
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryEventRecord:
    event_id: str
    incident_id: str
    action: str
    result: str
    detail: str
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IntegrityCheckRecord:
    check_id: str
    target_layer: str
    check_type: str
    result: str
    evidence: dict
    checked_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReliabilityMetricRecord:
    metric_id: str
    metric_name: str
    value: float
    unit: str
    source_reference: str
    is_observation: bool  # 항상 True — 관찰만, 자동 결정 없음
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PostmortemEventRecord:
    postmortem_event_id: str
    postmortem_id: str
    incident_id: str
    root_cause: str
    impact: str
    lesson: str
    from_state: str
    to_state: str
    reviewer: str
    note: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReliabilityReportRecord:
    report_id: str
    scope: str
    incident_count: int
    open_incident_count: int
    resolved_incident_count: int
    recovery_plan_count: int
    recovery_event_count: int
    integrity_check_count: int
    failed_check_count: int
    postmortem_count: int
    severity_distribution: dict
    category_distribution: dict
    reliability_metrics: dict
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
class ReliabilitySummary:
    timestamp: str
    incident_event_count: int
    incident_count: int
    recovery_plan_count: int
    recovery_event_count: int
    integrity_check_count: int
    reliability_metric_count: int
    postmortem_event_count: int
    postmortem_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
