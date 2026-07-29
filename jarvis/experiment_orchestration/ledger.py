"""Experiment Orchestration 원장 (P31) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 exo_ 접두사(EXperiment Orchestration). 각 레코드: id · timestamp · previous_hash · record_hash.
조정 기록만 — 실험 실행·거래·배포 없음. 상위 계층(P10~P30)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

PLANS = ("exo_plans.jsonl", "plan_event_id")                     # 실험 계획 생애주기(ES)
SCHEDULES = ("exo_schedules.jsonl", "schedule_id")             # 스케줄
DEPENDENCIES = ("exo_dependencies.jsonl", "dependency_id")     # 의존성
REQUESTS = ("exo_requests.jsonl", "request_event_id")         # 실행 요청 생애주기(ES, 사람 승인)
HISTORY = ("exo_history.jsonl", "history_id")                 # 실험 이력
REPORTS = ("exo_reports.jsonl", "report_id")                  # 조정 리포트
ARTIFACTS = ("exo_artifacts.jsonl", "artifact_id")           # 계보

ALL_LEDGERS = (PLANS, SCHEDULES, DEPENDENCIES, REQUESTS, HISTORY, REPORTS, ARTIFACTS)

# ── 조정 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "strategy_generation": ("rsg_candidates.jsonl", "candidate_event_id"),  # P29
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),          # P25
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),     # P22
    "production_readiness": ("pd_candidates.jsonl", "candidate_id"),       # P21
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),           # P24
    "simulation": ("sim_scenarios.jsonl", "event_id"),                     # P10.8
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


append_plan_event, read_plan_events, plans_head, plan_event_exists = _readers(PLANS)
append_schedule, read_schedules, schedules_head, schedule_exists = _readers(SCHEDULES)
append_dependency, read_dependencies, dependencies_head, dependency_exists = _readers(DEPENDENCIES)
append_request_event, read_request_events, requests_head, request_event_exists = _readers(REQUESTS)
append_history, read_history, history_head, history_exists = _readers(HISTORY)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def plan_events(plan) -> list[dict]:
    return [r for r in read_plan_events() if r.get("plan_id") == plan]


def plan_ids() -> list[str]:
    return sorted({r.get("plan_id") for r in read_plan_events() if r.get("plan_id")})


def request_events(req) -> list[dict]:
    return [r for r in read_request_events() if r.get("request_id") == req]


def request_ids() -> list[str]:
    return sorted({r.get("request_id") for r in read_request_events() if r.get("request_id")})


def schedules_for(plan) -> list[dict]:
    return [r for r in read_schedules() if r.get("plan_id") == plan]


def dependencies_for(plan) -> list[dict]:
    return [r for r in read_dependencies() if r.get("plan_id") == plan]


def requests_for(plan) -> list[dict]:
    return sorted({r.get("request_id") for r in read_request_events() if r.get("plan_id") == plan})


def history_for(plan) -> list[dict]:
    return [r for r in read_history() if r.get("plan_id") == plan]


def all_dependency_edges() -> list:
    return [(d.get("plan_id"), d.get("depends_on")) for d in read_dependencies()]
