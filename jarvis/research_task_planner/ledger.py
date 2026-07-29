"""Research Task Planner 원장 (P11.2) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rtp_ 접두사(Research Task Planner). 각 레코드: id · timestamp · previous_hash · record_hash. AI 에이전트
연구 워크플로 계획 — 계획만, 실행/자동승인/자동배포 없음. 계획은 불변(REQUESTED 이후 그래프 동결). Research OS/
상위 계층은 참조하지 않으며(순수 계획), 필요한 입력은 호출자가 전달한다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rtp_ 접두사)
PLANS = ("rtp_plans.jsonl", "plan_event_id")          # Plans (event-sourced lifecycle)
TASKS = ("rtp_tasks.jsonl", "task_id")                # Tasks
DEPENDENCIES = ("rtp_dependencies.jsonl", "dependency_id")  # Dependencies
SCHEDULES = ("rtp_schedules.jsonl", "schedule_id")    # Schedules
REPORTS = ("rtp_reports.jsonl", "report_id")          # Reports

ALL_LEDGERS = (PLANS, TASKS, DEPENDENCIES, SCHEDULES, REPORTS)


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


# ── Plans (lifecycle events) ──
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


# ── Tasks ──
def append_task(rec: dict) -> None:
    _append(TASKS[0], rec)


def read_tasks() -> list[dict]:
    return read_jsonl(TASKS[0])


def tasks_head() -> dict | None:
    return _head(TASKS[0])


def task_exists(task_id: str) -> bool:
    return _exists(TASKS[0], TASKS[1], task_id)


def get_task(task_id: str) -> dict | None:
    return _get(TASKS[0], TASKS[1], task_id)


def plan_tasks(plan_id: str) -> list[dict]:
    return [r for r in read_tasks() if r.get("plan_id") == plan_id]


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


def get_dependency(dependency_id: str) -> dict | None:
    return _get(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


def plan_dependencies(plan_id: str) -> list[dict]:
    return [r for r in read_dependencies() if r.get("plan_id") == plan_id]


# ── Schedules ──
def append_schedule(rec: dict) -> None:
    _append(SCHEDULES[0], rec)


def read_schedules() -> list[dict]:
    return read_jsonl(SCHEDULES[0])


def schedules_head() -> dict | None:
    return _head(SCHEDULES[0])


def schedule_exists(schedule_id: str) -> bool:
    return _exists(SCHEDULES[0], SCHEDULES[1], schedule_id)


def get_schedule(schedule_id: str) -> dict | None:
    return _get(SCHEDULES[0], SCHEDULES[1], schedule_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


def get_report(report_id: str) -> dict | None:
    return _get(REPORTS[0], REPORTS[1], report_id)
