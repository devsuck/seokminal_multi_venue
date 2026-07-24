"""Autonomous Research Manager 원장 (P12.9) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rmgr_ 접두사(Research ManaGeR). 각 레코드: id · timestamp · previous_hash · record_hash. 계획·추적·
모니터링만 — 거래/주문/배포 없음. 상위 계층은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rmgr_ 접두사)
PLANS = ("rmgr_plans.jsonl", "plan_event_id")                # Research Plans(event-sourced)
TASKS = ("rmgr_tasks.jsonl", "task_id")                      # Research Task Registry
DEPENDENCIES = ("rmgr_dependencies.jsonl", "dependency_id")  # Dependencies
PROGRESS = ("rmgr_progress.jsonl", "progress_id")            # Progress Tracking
REPORTS = ("rmgr_reports.jsonl", "report_id")                # Status Reports
ARTIFACTS = ("rmgr_artifacts.jsonl", "artifact_id")          # Artifact Lineage

ALL_LEDGERS = (PLANS, TASKS, DEPENDENCIES, PROGRESS, REPORTS, ARTIFACTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
    "research_experience_memory": ("rxm_memories.jsonl", "memory_event_id"),  # P12.7
    "research_learning": ("rll_loops.jsonl", "loop_event_id"),               # P12.8
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
def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


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


def task_dependencies(task_id: str) -> list[dict]:
    return [r for r in read_dependencies() if r.get("task_id") == task_id]


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


def plan_progress(plan_id: str) -> list[dict]:
    return [r for r in read_progress() if r.get("plan_id") == plan_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
