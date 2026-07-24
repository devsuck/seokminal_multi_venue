"""Research Coordinator 원장 (P11.7) — 11개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rco_ 접두사(Research COordinator). 각 레코드: id · timestamp · previous_hash · record_hash. 다중 연구
에이전트 조율 — 배정·의존성·진행·재분배·정체탐지·리포트만, 실행/거래/배포/상위 상태 변경 없음. 상위 계층은
수정하지 않는다(자족적 조율).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rco_ 접두사)
COORDINATORS = ("rco_coordinators.jsonl", "coordinator_id")   # Coordinator Registry
PLANS = ("rco_plans.jsonl", "plan_event_id")                  # Research Plans (event-sourced)
ASSIGNMENTS = ("rco_assignments.jsonl", "assignment_event_id")  # Task Assignments (event-sourced)
DEPENDENCIES = ("rco_dependencies.jsonl", "dependency_id")    # Dependency Graph
PROGRESS = ("rco_progress.jsonl", "progress_id")             # Progress Tracker
SCHEDULES = ("rco_schedules.jsonl", "schedule_id")           # Scheduling Metadata
WORKLOADS = ("rco_workloads.jsonl", "workload_id")           # Workload Metadata
EVENTS = ("rco_events.jsonl", "event_id")                    # Coordination Events
ESCALATIONS = ("rco_escalations.jsonl", "escalation_id")     # Escalation Records
REPORTS = ("rco_reports.jsonl", "report_id")                 # Completion Reports
ARTIFACTS = ("rco_artifacts.jsonl", "artifact_id")           # Coordinator Lineage

ALL_LEDGERS = (COORDINATORS, PLANS, ASSIGNMENTS, DEPENDENCIES, PROGRESS, SCHEDULES, WORKLOADS,
               EVENTS, ESCALATIONS, REPORTS, ARTIFACTS)


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


# ── Coordinators ──
def append_coordinator(rec: dict) -> None:
    _append(COORDINATORS[0], rec)


def read_coordinators() -> list[dict]:
    return read_jsonl(COORDINATORS[0])


def coordinators_head() -> dict | None:
    return _head(COORDINATORS[0])


def coordinator_exists(coordinator_id: str) -> bool:
    return _exists(COORDINATORS[0], COORDINATORS[1], coordinator_id)


def get_coordinator(coordinator_id: str) -> dict | None:
    return _get(COORDINATORS[0], COORDINATORS[1], coordinator_id)


# ── Plans (event-sourced) ──
def append_plan_event(rec: dict) -> None:
    _append(PLANS[0], rec)


def read_plan_events() -> list[dict]:
    return read_jsonl(PLANS[0])


def plans_head() -> dict | None:
    return _head(PLANS[0])


def plan_event_exists(plan_event_id: str) -> bool:
    return _exists(PLANS[0], PLANS[1], plan_event_id)


def plan_events(plan_id: str) -> list[dict]:
    return [r for r in read_plan_events() if r.get("plan_id") == plan_id]


def plan_ids() -> list[str]:
    return sorted({r.get("plan_id") for r in read_plan_events() if r.get("plan_id")})


# ── Assignments (event-sourced) ──
def append_assignment(rec: dict) -> None:
    _append(ASSIGNMENTS[0], rec)


def read_assignments() -> list[dict]:
    return read_jsonl(ASSIGNMENTS[0])


def assignments_head() -> dict | None:
    return _head(ASSIGNMENTS[0])


def assignment_event_exists(assignment_event_id: str) -> bool:
    return _exists(ASSIGNMENTS[0], ASSIGNMENTS[1], assignment_event_id)


def task_events(task_id: str) -> list[dict]:
    return [r for r in read_assignments() if r.get("task_id") == task_id]


def plan_task_ids(plan_id: str) -> list[str]:
    return sorted({r.get("task_id") for r in read_assignments() if r.get("plan_id") == plan_id})


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


def plan_dependencies(plan_id: str) -> list[dict]:
    return [r for r in read_dependencies() if r.get("plan_id") == plan_id]


# ── Progress ──
def append_progress(rec: dict) -> None:
    _append(PROGRESS[0], rec)


def read_progress() -> list[dict]:
    return read_jsonl(PROGRESS[0])


def progress_head() -> dict | None:
    return _head(PROGRESS[0])


def progress_exists(progress_id: str) -> bool:
    return _exists(PROGRESS[0], PROGRESS[1], progress_id)


def task_progress(task_id: str) -> list[dict]:
    return [r for r in read_progress() if r.get("task_id") == task_id]


# ── Schedules ──
def append_schedule(rec: dict) -> None:
    _append(SCHEDULES[0], rec)


def read_schedules() -> list[dict]:
    return read_jsonl(SCHEDULES[0])


def schedules_head() -> dict | None:
    return _head(SCHEDULES[0])


def schedule_exists(schedule_id: str) -> bool:
    return _exists(SCHEDULES[0], SCHEDULES[1], schedule_id)


def plan_schedules(plan_id: str) -> list[dict]:
    return [r for r in read_schedules() if r.get("plan_id") == plan_id]


# ── Workloads ──
def append_workload(rec: dict) -> None:
    _append(WORKLOADS[0], rec)


def read_workloads() -> list[dict]:
    return read_jsonl(WORKLOADS[0])


def workloads_head() -> dict | None:
    return _head(WORKLOADS[0])


def workload_exists(workload_id: str) -> bool:
    return _exists(WORKLOADS[0], WORKLOADS[1], workload_id)


def plan_workloads(plan_id: str) -> list[dict]:
    return [r for r in read_workloads() if r.get("plan_id") == plan_id]


# ── Coordination Events ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(event_id: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], event_id)


def plan_events_log(plan_id: str) -> list[dict]:
    return [r for r in read_events() if r.get("plan_id") == plan_id]


# ── Escalations ──
def append_escalation(rec: dict) -> None:
    _append(ESCALATIONS[0], rec)


def read_escalations() -> list[dict]:
    return read_jsonl(ESCALATIONS[0])


def escalations_head() -> dict | None:
    return _head(ESCALATIONS[0])


def escalation_exists(escalation_id: str) -> bool:
    return _exists(ESCALATIONS[0], ESCALATIONS[1], escalation_id)


def plan_escalations(plan_id: str) -> list[dict]:
    return [r for r in read_escalations() if r.get("plan_id") == plan_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (lineage) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
