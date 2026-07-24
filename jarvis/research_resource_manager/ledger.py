"""Research Resource Manager 원장 (P32) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rrm_ 접두사(Research Resource Manager). 각 레코드: id · timestamp · previous_hash · record_hash.
자원 추적 기록만 — 자동 배분·프로비저닝·실행 없음. 상위 계층(P10~P31)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

RESOURCES = ("rrm_resources.jsonl", "resource_id")               # 자원 레지스트리
USAGE = ("rrm_usage.jsonl", "usage_id")                         # 사용 기록
BUDGETS = ("rrm_budgets.jsonl", "budget_id")                   # 예산 기록
ALLOCATIONS = ("rrm_allocations.jsonl", "allocation_id")       # 배분 기록(자동 없음)
REPORTS = ("rrm_reports.jsonl", "report_id")                  # 자원 리포트
ARTIFACTS = ("rrm_artifacts.jsonl", "artifact_id")           # 계보

ALL_LEDGERS = (RESOURCES, USAGE, BUDGETS, ALLOCATIONS, REPORTS, ARTIFACTS)

# ── 자원 관측 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "strategy_generation": ("rsg_candidates.jsonl", "candidate_event_id"),  # P29
    "experiment_orchestration": ("exo_plans.jsonl", "plan_event_id"),      # P31
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),          # P25
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),     # P22
    "production_readiness": ("pd_candidates.jsonl", "candidate_id"),       # P21
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


append_resource, read_resources, resources_head, resource_exists = _readers(RESOURCES)
append_usage, read_usage, usage_head, usage_exists = _readers(USAGE)
append_budget, read_budgets, budgets_head, budget_exists = _readers(BUDGETS)
append_allocation, read_allocations, allocations_head, allocation_exists = _readers(ALLOCATIONS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def usage_for(resource) -> list[dict]:
    return [r for r in read_usage() if r.get("resource_id") == resource]


def allocations_for(resource) -> list[dict]:
    return [r for r in read_allocations() if r.get("resource_id") == resource]


def resource_ids() -> list[str]:
    return sorted({r.get("resource_id") for r in read_resources() if r.get("resource_id")})


def resource_by_id(resource):
    return next((r for r in read_resources() if r.get("resource_id") == resource), None)
