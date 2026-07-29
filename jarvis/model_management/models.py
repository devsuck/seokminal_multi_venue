"""Model Management Layer 자료형 (P43) — AI/ML 모델 생애주기 관리. **라이브 배포 없음.**

AI/ML 모델 생애주기를 관리한다: 모델·모델 버전·검증 결과·성능 이력·모델 메타데이터. **라이브 배포 없음 — 연구용 관리만.**
MANAGED ≠ DEPLOYED · AVAILABLE_FOR_RESEARCH ≠ LIVE. 불변·append-only·SHA256 해시체인·이벤트 소싱·결정적. 물리 원장
mdl_ 접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 모델 생애주기(4) — 이벤트 소싱 ──
M_REGISTERED = "REGISTERED"
M_VALIDATED = "VALIDATED"
M_AVAILABLE = "AVAILABLE_FOR_RESEARCH"
M_ARCHIVED = "ARCHIVED"
MODEL_STATES = (M_REGISTERED, M_VALIDATED, M_AVAILABLE, M_ARCHIVED)
MODEL_TRANSITIONS = {
    M_REGISTERED: {M_VALIDATED},
    M_VALIDATED: {M_VALIDATED, M_AVAILABLE},
    M_AVAILABLE: {M_AVAILABLE, M_ARCHIVED},
    M_ARCHIVED: set(),
}

# ── 모델 유형 ──
MODEL_TYPES = ("CLASSIFIER", "REGRESSOR", "FORECASTER", "ANOMALY_DETECTOR", "RANKER", "GENERATIVE")
# ── 검증 항목 ──
VALIDATION_CHECKS = ("ACCURACY", "ROBUSTNESS", "CALIBRATION", "LEAKAGE", "STABILITY")

# ── 아티팩트 유형(계보) ──
ART_MODEL = "MODEL"
ART_VERSION = "MODEL_VERSION"
ART_REPORT = "REPORT"

# ── 절대 금지(거래·실행·배포·배분) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "DEPLOY_MODEL",
    "SERVE_LIVE", "PROMOTE",
})


class ImmutableModelError(Exception):
    """불변 모델(중복 genesis) 위반."""


class IllegalModelTransition(Exception):
    """유효하지 않은 모델 전이 — 차단."""


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


def artifact_content_hash(payload) -> str:
    return _digest({"payload": payload})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (MM* 스킴) ──
def model_id(name) -> str:
    return _id("MMM", name)


def model_event_id(mdl, to, seq) -> str:
    return _id("MME", mdl, to, seq)


def version_id(mdl, version) -> str:
    return _id("MMV", mdl, version)


def validation_id(mdl, check, seq) -> str:
    return _id("MML", mdl, check, seq)


def performance_id(mdl, metric, seq) -> str:
    return _id("MMP", mdl, metric, seq)


def metadata_id(mdl, key) -> str:
    return _id("MMD", mdl, key)


def report_id(scope, created_at) -> str:
    return _id("MMR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("MMA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_model_transition(frm, to) -> bool:
    return to in MODEL_TRANSITIONS.get(frm, set())


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


def metric_delta(a, b) -> float:
    try:
        return round(float(b) - float(a), 6)
    except (TypeError, ValueError):
        return 0.0


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
class ModelEventRecord:
    model_event_id: str
    model_id: str
    name: str
    model_type: str
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
class ModelVersionRecord:
    version_id: str
    model_id: str
    version: str
    content_hash: str
    framework: str
    parent_version: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResultRecord:
    validation_id: str
    model_id: str
    version_id: str
    check: str
    passed: bool
    score: float
    details: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PerformanceRecord:
    performance_id: str
    model_id: str
    version_id: str
    metric: str
    value: float
    dataset_ref: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelMetadataRecord:
    metadata_id: str
    model_id: str
    key: str
    value: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelReportRecord:
    report_id: str
    scope: str
    model_count: int
    available_model_count: int
    version_count: int
    validation_count: int
    performance_count: int
    metadata_count: int
    type_distribution: dict
    state_distribution: dict
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
class ModelSummary:
    timestamp: str
    model_event_count: int
    model_count: int
    version_count: int
    validation_count: int
    performance_count: int
    metadata_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
