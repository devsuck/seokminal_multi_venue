"""Research API Gateway 자료형 (P33) — 통합 읽기 전용 API 계층. **동작 없음.**

통합 API 계층. 읽기 전용 서비스만 노출한다: 지식 질의·연구 요약·이력·지표·리포트·계보. **거래·배포·실행·승인·배분을
노출하지 않는다.** READ ONLY · GATEWAY ≠ EXECUTION · QUERY ≠ MUTATION. 불변·append-only·SHA256 해시체인·결정적.
물리 원장 rgw_ 접두사. 상위 계층(P10~P32)은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 노출 가능한 읽기 전용 서비스 유형 ──
SERVICE_TYPES = ("KNOWLEDGE_QUERY", "RESEARCH_SUMMARY", "HISTORY", "METRICS", "REPORTS", "LINEAGE")
# ── 절대 노출 금지 서비스 유형(변경·실행) ──
FORBIDDEN_SERVICE_TYPES = ("TRADE", "DEPLOY", "EXECUTE", "APPROVE", "ALLOCATE", "PROVISION",
                           "MUTATE", "WRITE")

# ── 아티팩트 유형 ──
ART_SERVICE = "SERVICE"
ART_QUERY = "QUERY"
ART_REPORT = "REPORT"

# ── 절대 금지(실행·배포·거래·승인·배분) 동사 — 탐지용 ──
FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "PROVISION",
    "MUTATE", "WRITE_UPSTREAM", "PROMOTE",
})


class ForbiddenServiceError(Exception):
    """변경·실행 서비스 노출 시도 — 차단(읽기 전용 게이트웨이)."""


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


# ── 결정적 ID (GW* 스킴) ──
def service_id(service_type, name) -> str:
    return _id("GWS", service_type, name)


def query_id(service_type, target_layer, seq) -> str:
    return _id("GWQ", service_type, target_layer, seq)


def response_id(query) -> str:
    return _id("GWP", query)


def report_id(scope, created_at) -> str:
    return _id("GWR", scope, created_at)


def artifact_id(atype, ref) -> str:
    return _id("GWA", atype, ref)


# ── 결정적 분석 함수 ──
def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def is_readonly_service(service_type) -> bool:
    return service_type in SERVICE_TYPES and service_type not in FORBIDDEN_SERVICE_TYPES


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
class ServiceRecord:
    service_id: str
    service_type: str
    name: str
    description: str
    is_readonly: bool  # 항상 True — 읽기 전용만 노출
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QueryRecord:
    query_id: str
    service_type: str
    target_layer: str
    params: dict
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResponseRecord:
    response_id: str
    query_id: str
    service_type: str
    target_layer: str
    result_count: int
    result_summary: dict
    is_readonly: bool  # 항상 True — 응답은 읽기 결과만
    timestamp: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GatewayReportRecord:
    report_id: str
    scope: str
    service_count: int
    query_count: int
    response_count: int
    service_type_distribution: dict
    layer_distribution: dict
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
class GatewaySummary:
    timestamp: str
    service_count: int
    query_count: int
    response_count: int
    report_count: int
    artifact_count: int

    def to_dict(self) -> dict:
        return asdict(self)
