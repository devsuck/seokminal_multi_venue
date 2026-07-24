"""Real Data Infrastructure 자료형 (P41) — 시장 연구 데이터 인프라. **거래 연결 없음.**

신뢰할 수 있는 시장 연구 데이터 인프라를 구축한다: 데이터 수집·역사적 저장·데이터 검증·데이터셋 버전관리·피처 준비.
DataSource·Dataset·DatasetVersion·FeatureSet·QualityReport·Lineage 를 소유한다. **거래 연결 없음 — 데이터 메타·
검증 기록만.** DATA ≠ TRADING · METADATA ≠ EXECUTION. append-only 메타·해시 검증·데이터셋 계보·재현. 물리 원장 dinf_
접두사. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 데이터셋 생애주기(4) — 이벤트 소싱 ──
D_CREATED = "CREATED"
D_VALIDATED = "VALIDATED"
D_AVAILABLE = "AVAILABLE"
D_ARCHIVED = "ARCHIVED"
DATASET_STATES = (D_CREATED, D_VALIDATED, D_AVAILABLE, D_ARCHIVED)
DATASET_TRANSITIONS = {
    D_CREATED: {D_VALIDATED},
    D_VALIDATED: {D_VALIDATED, D_AVAILABLE},
    D_AVAILABLE: {D_AVAILABLE, D_ARCHIVED},
    D_ARCHIVED: set(),
}

# ── 데이터 소스 유형 ──
SOURCE_TYPES = ("MARKET_DATA", "ALTERNATIVE", "FUNDAMENTAL", "DERIVED", "REFERENCE")
# ── 품질 차원 ──
QUALITY_DIMENSIONS = ("COMPLETENESS", "ACCURACY", "CONSISTENCY", "TIMELINESS", "VALIDITY")

# ── 아티팩트 유형(계보) ──
ART_SOURCE = "DATA_SOURCE"
ART_DATASET = "DATASET"
ART_VERSION = "DATASET_VERSION"
ART_FEATURE = "FEATURE_SET"
ART_REPORT = "REPORT"

# ── 절대 금지(거래·실행·배포·배분) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "PROMOTE",
})


class ImmutableDatasetError(Exception):
    """불변 데이터셋(중복 genesis) 위반."""


class IllegalDatasetTransition(Exception):
    """유효하지 않은 데이터셋 전이 — 차단."""


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


def data_content_hash(payload) -> str:
    """데이터셋 버전 내용 해시(재현성·계보)."""
    return _digest({"payload": payload})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


# ── 결정적 ID (DT* 스킴) ──
def source_id(source_type, name) -> str:
    return _id("DTS", source_type, name)


def dataset_id(name) -> str:
    return _id("DTD", name)


def dataset_event_id(ds, to, seq) -> str:
    return _id("DTE", ds, to, seq)


def version_id(ds, version) -> str:
    return _id("DTV", ds, version)


def feature_set_id(ds, name) -> str:
    return _id("DTF", ds, name)


def quality_id(ds, dimension, seq) -> str:
    return _id("DTQ", ds, dimension, seq)


def report_id(scope, created_at) -> str:
    return _id("DTR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("DTA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def can_dataset_transition(frm, to) -> bool:
    return to in DATASET_TRANSITIONS.get(frm, set())


def clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, v)), 6)


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
class DataSourceRecord:
    source_id: str
    name: str
    source_type: str
    uri_ref: str
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DatasetEventRecord:
    dataset_event_id: str
    dataset_id: str
    name: str
    source_id: str
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
class DatasetVersionRecord:
    version_id: str
    dataset_id: str
    version: str
    content_hash: str
    row_count: int
    schema_hash: str
    parent_version: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeatureSetRecord:
    feature_set_id: str
    dataset_id: str
    version_id: str
    features: list
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QualityReportRecord:
    quality_id: str
    dataset_id: str
    version_id: str
    dimension: str
    score: float
    passed: bool
    issues: list
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataInfraReportRecord:
    report_id: str
    scope: str
    source_count: int
    dataset_count: int
    available_dataset_count: int
    version_count: int
    feature_set_count: int
    quality_count: int
    source_type_distribution: dict
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
class DataInfraSummary:
    timestamp: str
    source_count: int
    dataset_event_count: int
    dataset_count: int
    version_count: int
    feature_set_count: int
    quality_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
