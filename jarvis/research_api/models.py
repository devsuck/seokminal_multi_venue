"""Research Intelligence API Backend 자료형 (P10.29) — 대시보드·AI 에이전트용 백엔드 인터페이스. **읽기 전용.**

상위 거버넌스·인텔리전스 계층(P10.23~P10.28)을 **READ ONLY** 로 참조(파일 기반, import 없음)해 시스템 상태·연구
타임라인·전략 계보·알파/리스크/에이전트 요약·거버넌스 리포트를 조회 API 로 제공한다. **API·데이터 접근 전용 —
거래 실행 없음.** POST 실행·trade·order·deployment 엔드포인트 없음. GET(읽기)만. READ ≠ WRITE · QUERY ≠ EXECUTE ·
API ≠ TRADE. 접근 감사 원장은 append-only·불변·해시체인. 물리 원장은 rapi_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── HTTP 메서드(읽기만 허용) ──
METHOD_GET = "GET"
ALLOWED_METHODS = (METHOD_GET,)
# 실행/변경 메서드는 등록 불가.
FORBIDDEN_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# ── 금지 엔드포인트 동사(실행·거래·주문·배포) ──
FORBIDDEN_VERBS = ("execute", "trade", "order", "deploy", "allocate", "place",
                   "submit_order", "activate", "liquidate", "rebalance")

# ── 필드 타입(스키마) ──
T_INT = "int"
T_FLOAT = "float"
T_STR = "str"
T_LIST = "list"
T_DICT = "dict"
T_BOOL = "bool"
FIELD_TYPES = (T_INT, T_FLOAT, T_STR, T_LIST, T_DICT, T_BOOL)

# ── 엔드포인트 → 응답 스키마 필드(권위 있는 키 집합) ──
ENDPOINT_SCHEMAS = {
    "get_system_status": ("component_count", "active_component_count", "dependency_count",
                          "health_level", "overall_score", "category_distribution",
                          "last_snapshot_at"),
    "get_research_timeline": ("events", "event_count", "truncated"),
    "get_strategy_lineage": ("strategy", "stages", "stage_count"),
    "get_alpha_summary": ("insight_count", "insight_type_distribution", "pattern_count",
                          "cluster_count", "recommendation_count"),
    "get_risk_summary": ("assessment_count", "result_distribution", "factor_count"),
    "get_agent_summary": ("audit_count", "check_count", "violation_count", "result_distribution"),
    "get_governance_report": ("layer_count", "report_count", "conflict_count", "health_level"),
}

# ── 엔드포인트 메타(function, path, source_layers) — 전부 GET·read_only ──
ENDPOINT_META = (
    ("get_system_status", "/api/v1/system/status", ("research_control_plane",)),
    ("get_research_timeline", "/api/v1/research/timeline",
     ("research_control_plane", "research_lifecycle")),
    ("get_strategy_lineage", "/api/v1/strategy/lineage", ("research_lifecycle",)),
    ("get_alpha_summary", "/api/v1/alpha/summary", ("knowledge_intelligence",)),
    ("get_risk_summary", "/api/v1/risk/summary", ("research_risk_intelligence",)),
    ("get_agent_summary", "/api/v1/agent/summary", ("self_audit_intelligence",)),
    ("get_governance_report", "/api/v1/governance/report", ("governance_orchestration",)),
)


class ImmutableSchemaError(Exception):
    """불변 API 스키마 위반."""


class ImmutableQueryError(Exception):
    """불변 쿼리 위반."""


class ImmutableViewError(Exception):
    """불변 대시보드 뷰 위반."""


class ImmutableEndpointError(Exception):
    """불변 엔드포인트 메타 위반."""


class InvalidEndpointMethod(Exception):
    """허용되지 않은 HTTP 메서드(GET 외) — 실행/변경 불가."""


class ForbiddenEndpoint(Exception):
    """금지 엔드포인트(실행·거래·주문·배포)."""


class InvalidFieldType(Exception):
    """미등록 필드 타입."""


class UnknownEndpointError(Exception):
    """미등록 엔드포인트 호출."""


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


def result_hash(data: dict) -> str:
    """응답 데이터의 결정적 해시(생성 시각 제외)."""
    return _digest(data)


def params_hash(params: dict) -> str:
    return _digest(params or {})


# ── 결정적 ID ──
def schema_id(name: str) -> str:
    return "RAS:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def query_id(name: str) -> str:
    return "RAQ:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def view_id(name: str) -> str:
    return "RAV:" + hashlib.sha1(input_digest(name).encode()).hexdigest()[:12]


def endpoint_id(path: str) -> str:
    return "RAE:" + hashlib.sha1(input_digest(path).encode()).hexdigest()[:12]


def access_id(endpoint: str, phash: str, accessed_at: str) -> str:
    return "RAL:" + hashlib.sha1(
        input_digest(endpoint, phash, accessed_at).encode()).hexdigest()[:12]


# ── 결정적 유틸 ──
def is_forbidden_path(path: str, function: str = "") -> bool:
    """실행·거래·주문·배포 동사 포함 여부(결정적). **금지 엔드포인트 탐지.**"""
    blob = f"{path} {function}".lower()
    return any(v in blob for v in FORBIDDEN_VERBS)


def distribution(records: list, fields) -> dict:
    """레코드에서 첫 존재 필드값 분포(결정적 정렬). 없으면 빈 dict."""
    key = None
    for f in fields:
        if any(f in r for r in records):
            key = f
            break
    if key is None:
        return {}
    out: dict = {}
    for r in records:
        v = r.get(key)
        if v is None:
            continue
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class SchemaRecord:
    schema_id: str
    name: str
    endpoint: str
    fields: list
    version: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QueryRecord:
    query_id: str
    name: str
    source_layer: str
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ViewRecord:
    view_id: str
    name: str
    endpoint: str
    columns: list
    refresh_hint: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EndpointRecord:
    endpoint_id: str
    path: str
    method: str
    function: str
    source_layers: list
    read_only: bool
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AccessLogRecord:
    access_id: str
    endpoint: str
    method: str
    params_hash: str
    result_hash: str
    read_only: bool
    accessed_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class APIResponse:
    endpoint: str
    schema_id: str
    read_only: bool
    data: dict
    result_hash: str
    disclaimer: str
    generated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class APISummary:
    timestamp: str
    schema_count: int
    query_count: int
    view_count: int
    endpoint_count: int
    access_count: int

    def to_dict(self) -> dict:
        return asdict(self)
