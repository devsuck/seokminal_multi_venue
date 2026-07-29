"""Research API 원장 (P10.29) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rapi_ 접두사(Research API). 각 레코드: id · timestamp · previous_hash · record_hash. 대시보드·AI
에이전트용 조회 백엔드 — API·데이터 접근만, 거래 실행 없음. 상위 소스(P10.23~P10.28)는 **READ ONLY** — 파일만
읽고 절대 쓰지 않는다. import 결합 없음. 접근 감사(rapi_access)는 append-only 감사 로그.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rapi_ 접두사)
SCHEMAS = ("rapi_schemas.jsonl", "schema_id")
QUERIES = ("rapi_queries.jsonl", "query_id")
VIEWS = ("rapi_views.jsonl", "view_id")
ENDPOINTS = ("rapi_endpoints.jsonl", "endpoint_id")
ACCESS = ("rapi_access.jsonl", "access_id")

ALL_LEDGERS = (SCHEMAS, QUERIES, VIEWS, ENDPOINTS, ACCESS)

# ── 상위 소스 원장(READ ONLY) — P10.23~P10.28. import 결합 없음, 파일만 읽는다. ──
# {layer: {role: (filename, id_field)}}
SOURCE_LEDGERS = {
    "governance_orchestration": {  # P10.23
        "layers": ("go_layers.jsonl", "event_id"),
        "health": ("go_health.jsonl", "health_id"),
        "conflicts": ("go_conflicts.jsonl", "conflict_id"),
        "reports": ("go_reports.jsonl", "report_id"),
    },
    "self_audit_intelligence": {  # P10.24
        "audits": ("sa_audits.jsonl", "audit_id"),
        "checks": ("sa_checks.jsonl", "check_id"),
        "violations": ("sa_violations.jsonl", "violation_id"),
    },
    "research_risk_intelligence": {  # P10.25
        "assessments": ("rr_assessments.jsonl", "assessment_id"),
        "factors": ("rr_factors.jsonl", "factor_id"),
    },
    "research_lifecycle": {  # P10.26
        "events": ("rl_events.jsonl", "event_id"),
        "transitions": ("rl_transitions.jsonl", "transition_id"),
        "reports": ("rl_reports.jsonl", "report_id"),
    },
    "knowledge_intelligence": {  # P10.27
        "insights": ("ki_insights.jsonl", "insight_id"),
        "patterns": ("ki_patterns.jsonl", "pattern_id"),
        "clusters": ("ki_clusters.jsonl", "cluster_id"),
    },
    "research_control_plane": {  # P10.28
        "overview": ("rcp_overview.jsonl", "overview_id"),
        "health": ("rcp_health.jsonl", "health_id"),
        "timeline": ("rcp_timeline.jsonl", "event_id"),
    },
}


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename: str) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _head(filename: str) -> dict | None:
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def _get(filename: str, id_field: str, rid: str) -> dict | None:
    for r in read_jsonl(filename):
        if r.get(id_field) == rid:
            return r
    return None


# ── 상위 소스 READ ONLY ──
def source_exists(filename: str) -> bool:
    return os.path.exists(state_path(filename))


def read_source(filename: str) -> list[dict]:
    """상위 소스 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def read_role(layer: str, role: str) -> list[dict]:
    spec = SOURCE_LEDGERS.get(layer, {}).get(role)
    if not spec:
        return []
    return read_source(spec[0])


# ── Schemas ──
def append_schema(rec: dict) -> None:
    _append(SCHEMAS[0], rec)


def read_schemas() -> list[dict]:
    return read_jsonl(SCHEMAS[0])


def schemas_head() -> dict | None:
    return _head(SCHEMAS[0])


def schema_exists(schema_id: str) -> bool:
    return _exists(SCHEMAS[0], SCHEMAS[1], schema_id)


def get_schema(schema_id: str) -> dict | None:
    return _get(SCHEMAS[0], SCHEMAS[1], schema_id)


# ── Queries ──
def append_query(rec: dict) -> None:
    _append(QUERIES[0], rec)


def read_queries() -> list[dict]:
    return read_jsonl(QUERIES[0])


def queries_head() -> dict | None:
    return _head(QUERIES[0])


def query_exists(query_id: str) -> bool:
    return _exists(QUERIES[0], QUERIES[1], query_id)


def get_query(query_id: str) -> dict | None:
    return _get(QUERIES[0], QUERIES[1], query_id)


# ── Views ──
def append_view(rec: dict) -> None:
    _append(VIEWS[0], rec)


def read_views() -> list[dict]:
    return read_jsonl(VIEWS[0])


def views_head() -> dict | None:
    return _head(VIEWS[0])


def view_exists(view_id: str) -> bool:
    return _exists(VIEWS[0], VIEWS[1], view_id)


def get_view(view_id: str) -> dict | None:
    return _get(VIEWS[0], VIEWS[1], view_id)


# ── Endpoints ──
def append_endpoint(rec: dict) -> None:
    _append(ENDPOINTS[0], rec)


def read_endpoints() -> list[dict]:
    return read_jsonl(ENDPOINTS[0])


def endpoints_head() -> dict | None:
    return _head(ENDPOINTS[0])


def endpoint_exists(endpoint_id: str) -> bool:
    return _exists(ENDPOINTS[0], ENDPOINTS[1], endpoint_id)


def get_endpoint(endpoint_id: str) -> dict | None:
    return _get(ENDPOINTS[0], ENDPOINTS[1], endpoint_id)


# ── Access Logs (감사) ──
def append_access(rec: dict) -> None:
    _append(ACCESS[0], rec)


def read_access() -> list[dict]:
    return read_jsonl(ACCESS[0])


def access_head() -> dict | None:
    return _head(ACCESS[0])


def access_exists(access_id: str) -> bool:
    return _exists(ACCESS[0], ACCESS[1], access_id)
