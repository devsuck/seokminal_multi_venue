"""Research Operations 원장 (P18) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 ro_ 접두사(Research Operations). 각 레코드: id · timestamp · previous_hash · record_hash · metadata. 조정·
계획·추적만 — 실행·자동조치 없음. 상위/통합 계층(P10.5/P10.6/P10.7/P10.8/P17)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (ro_ 접두사)
WORKFLOWS = ("ro_workflows.jsonl", "workflow_event_id")       # 워크플로 생애주기(event-sourced)
TASKS = ("ro_tasks.jsonl", "task_event_id")                   # 작업 생애주기(event-sourced)
DEPENDENCIES = ("ro_dependencies.jsonl", "dependency_id")     # 작업 의존
RUNS = ("ro_runs.jsonl", "run_id")                            # 런 레코드
EXECUTION_PLANS = ("ro_execution_plans.jsonl", "plan_id")     # 실행 계획(제안)
EVENTS = ("ro_events.jsonl", "event_id")                      # 오케스트레이션 이벤트 로그
REPORTS = ("ro_reports.jsonl", "report_id")                   # 운영 리포트
ARTIFACTS = ("ro_artifacts.jsonl", "artifact_id")             # 아티팩트 계보

ALL_LEDGERS = (WORKFLOWS, TASKS, DEPENDENCIES, RUNS, EXECUTION_PLANS, EVENTS, REPORTS, ARTIFACTS)

# ── 통합 소스(READ ONLY) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "event_id"),           # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),           # P10.6
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),   # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),              # P10.8
    "observability": ("obs_pipeline_health.jsonl", "health_event_id"),  # P17
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


# ── 통합 소스 READ ONLY ──
def source_count(layer: str) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


# ── Workflows (event-sourced) ──
def append_workflow_event(rec: dict) -> None:
    _append(WORKFLOWS[0], rec)


def read_workflow_events() -> list[dict]:
    return read_jsonl(WORKFLOWS[0])


def workflows_head() -> dict | None:
    return _head(WORKFLOWS[0])


def workflow_event_exists(wid: str) -> bool:
    return _exists(WORKFLOWS[0], WORKFLOWS[1], wid)


def workflow_events(workflow_id: str) -> list[dict]:
    return [r for r in read_workflow_events() if r.get("workflow_id") == workflow_id]


def workflow_ids() -> list[str]:
    return sorted({r.get("workflow_id") for r in read_workflow_events() if r.get("workflow_id")})


# ── Tasks (event-sourced) ──
def append_task_event(rec: dict) -> None:
    _append(TASKS[0], rec)


def read_task_events() -> list[dict]:
    return read_jsonl(TASKS[0])


def tasks_head() -> dict | None:
    return _head(TASKS[0])


def task_event_exists(tid: str) -> bool:
    return _exists(TASKS[0], TASKS[1], tid)


def task_events(task_id: str) -> list[dict]:
    return [r for r in read_task_events() if r.get("task_id") == task_id]


def workflow_tasks(workflow_id: str) -> list[str]:
    return sorted({r.get("task_id") for r in read_task_events()
                   if r.get("workflow_id") == workflow_id and r.get("task_id")})


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(did: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], did)


# ── Runs ──
def append_run(rec: dict) -> None:
    _append(RUNS[0], rec)


def read_runs() -> list[dict]:
    return read_jsonl(RUNS[0])


def runs_head() -> dict | None:
    return _head(RUNS[0])


def run_exists(rid: str) -> bool:
    return _exists(RUNS[0], RUNS[1], rid)


def workflow_runs(workflow_id: str) -> list[dict]:
    return [r for r in read_runs() if r.get("workflow_id") == workflow_id]


# ── Execution Plans ──
def append_plan(rec: dict) -> None:
    _append(EXECUTION_PLANS[0], rec)


def read_plans() -> list[dict]:
    return read_jsonl(EXECUTION_PLANS[0])


def plans_head() -> dict | None:
    return _head(EXECUTION_PLANS[0])


def plan_exists(pid: str) -> bool:
    return _exists(EXECUTION_PLANS[0], EXECUTION_PLANS[1], pid)


# ── Events ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(eid: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], eid)


def workflow_event_log(workflow_id: str) -> list[dict]:
    return [r for r in read_events() if r.get("workflow_id") == workflow_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(rid: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], rid)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(aid: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], aid)
