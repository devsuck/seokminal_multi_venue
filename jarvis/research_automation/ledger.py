"""Research Automation 원장 (P22) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 ra_ 접두사(Research Automation). 각 레코드: id · timestamp · previous_hash · record_hash. 조정·기록만 —
실행·배포 없음. 상위/통합 계층(P10.2~P21)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

WORKFLOWS = ("ra_workflows.jsonl", "workflow_event_id")     # 워크플로 생애주기(ES)
PIPELINES = ("ra_pipelines.jsonl", "pipeline_event_id")     # 파이프라인 생애주기(ES)
TASKS = ("ra_tasks.jsonl", "task_event_id")                 # 작업 생애주기(ES)
RUNS = ("ra_runs.jsonl", "run_id")                          # 연구 실행 기록
DEPENDENCIES = ("ra_dependencies.jsonl", "dependency_id")   # 작업 의존(DAG)
EVENTS = ("ra_events.jsonl", "event_id")                    # 자동화 감사 추적
REPORTS = ("ra_reports.jsonl", "report_id")                 # 파이프라인 리포트
ARTIFACTS = ("ra_artifacts.jsonl", "artifact_id")           # 아티팩트 계보

ALL_LEDGERS = (WORKFLOWS, PIPELINES, TASKS, RUNS, DEPENDENCIES, EVENTS, REPORTS, ARTIFACTS)

# ── 통합 소스(READ ONLY) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "research_governance": ("rg_policies.jsonl", "policy_hash"),        # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),         # P10.3
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_hash"),   # P10.4
    "knowledge_graph": ("kg_entities.jsonl", "event_id"),              # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),              # P10.6
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),      # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                 # P10.8
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


# ── 통합 소스 READ ONLY ──
def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_ref_exists(layer, ref) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── helper 팩토리 ──
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


append_workflow_event, read_workflow_events, workflows_head, workflow_event_exists = _readers(WORKFLOWS)
append_pipeline_event, read_pipeline_events, pipelines_head, pipeline_event_exists = _readers(PIPELINES)
append_task_event, read_task_events, tasks_head, task_event_exists = _readers(TASKS)
append_run, read_runs, runs_head, run_exists = _readers(RUNS)
append_dependency, read_dependencies, dependencies_head, dependency_exists = _readers(DEPENDENCIES)
append_event, read_events, events_head, event_exists = _readers(EVENTS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def workflow_events(wf) -> list[dict]:
    return [r for r in read_workflow_events() if r.get("workflow_id") == wf]


def workflow_ids() -> list[str]:
    return sorted({r.get("workflow_id") for r in read_workflow_events() if r.get("workflow_id")})


def pipeline_events(pipe) -> list[dict]:
    return [r for r in read_pipeline_events() if r.get("pipeline_id") == pipe]


def workflow_pipelines(wf) -> list[str]:
    return sorted({r.get("pipeline_id") for r in read_pipeline_events()
                   if r.get("workflow_id") == wf and r.get("pipeline_id")})


def task_events(task) -> list[dict]:
    return [r for r in read_task_events() if r.get("task_id") == task]


def pipeline_tasks(pipe) -> list[str]:
    return sorted({r.get("task_id") for r in read_task_events()
                   if r.get("pipeline_id") == pipe and r.get("task_id")})


def pipeline_runs(pipe) -> list[dict]:
    return [r for r in read_runs() if r.get("pipeline_id") == pipe]
