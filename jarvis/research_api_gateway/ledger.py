"""Research API Gateway 원장 (P33) — 5개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rgw_ 접두사(Research GateWay). 각 레코드: id · timestamp · previous_hash · record_hash. 읽기 전용
서비스·질의·응답 감사 로그만 — 상위 원장 변경 없음. 상위 계층(P10~P32)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

SERVICES = ("rgw_services.jsonl", "service_id")                  # 읽기 전용 서비스 레지스트리
QUERIES = ("rgw_queries.jsonl", "query_id")                     # 질의 감사 로그
RESPONSES = ("rgw_responses.jsonl", "response_id")             # 응답 로그
REPORTS = ("rgw_reports.jsonl", "report_id")                  # 게이트웨이 리포트
ARTIFACTS = ("rgw_artifacts.jsonl", "artifact_id")           # 계보

ALL_LEDGERS = (SERVICES, QUERIES, RESPONSES, REPORTS, ARTIFACTS)

# ── 통합 노출 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),               # P10.5
    "memory_intelligence": ("rmi_memories.jsonl", "memory_event_id"),    # P27
    "insight_intelligence": ("rii_insights.jsonl", "insight_event_id"),  # P28
    "meta_intelligence": ("mri_meta_metrics.jsonl", "metric_id"),        # P30
    "monitoring": ("rmon_health_checks.jsonl", "health_id"),            # P23
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),        # P24
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),       # P25
    "strategy_generation": ("rsg_candidates.jsonl", "candidate_event_id"),  # P29
    "orchestration": ("exo_plans.jsonl", "plan_event_id"),             # P31
    "resource_manager": ("rrm_resources.jsonl", "resource_id"),        # P32
}


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
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


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename, id_field, rid) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_present(layer) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def source_records(layer) -> list[dict]:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return []
    return read_jsonl(spec[0])


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec)

    def read():
        return read_jsonl(fname)

    def head():
        return _head(fname)

    def exists(rid):
        return _exists(fname, idf, rid)

    return append, read, head, exists


append_service, read_services, services_head, service_exists = _readers(SERVICES)
append_query, read_queries, queries_head, query_exists = _readers(QUERIES)
append_response, read_responses, responses_head, response_exists = _readers(RESPONSES)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def queries_by(service_type, target_layer) -> list[dict]:
    return [r for r in read_queries()
            if r.get("service_type") == service_type and r.get("target_layer") == target_layer]
