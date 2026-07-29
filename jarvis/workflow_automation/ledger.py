"""Workflow Automation 원장 (P44) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 wf_ 접두사(WorkFlow). 각 레코드: id · timestamp · previous_hash · record_hash. 워크플로 생애주기·태스크·
의존성·검토 요청·메타 기록만 — 자율 실행 없음. 상위 계층은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

WORKFLOWS = ("wf_workflows.jsonl", "workflow_event_id")       # 워크플로 생애주기(ES)
TASKS = ("wf_tasks.jsonl", "task_event_id")                  # 태스크 상태(ES)
DEPENDENCIES = ("wf_dependencies.jsonl", "dependency_id")    # 의존성 엣지
APPROVALS = ("wf_approvals.jsonl", "approval_id")           # 사람 검토 요청(자동 승인 없음)
METADATA = ("wf_metadata.jsonl", "metadata_id")            # 워크플로 메타
REPORTS = ("wf_reports.jsonl", "report_id")               # 리포트
ARTIFACTS = ("wf_artifacts.jsonl", "artifact_id")        # 계보

ALL_LEDGERS = (WORKFLOWS, TASKS, DEPENDENCIES, APPROVALS, METADATA, REPORTS, ARTIFACTS)

# ── 참조 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "model_management": ("mdl_models.jsonl", "model_event_id"),          # P43
    "experiment_tracking": ("expt_experiments.jsonl", "experiment_id"),  # P42
    "data_infrastructure": ("dinf_datasets.jsonl", "dataset_event_id"),  # P41
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


append_workflow_event, read_workflow_events, workflows_head, workflow_event_exists = _readers(WORKFLOWS)
append_task_event, read_task_events, tasks_head, task_event_exists = _readers(TASKS)
append_dependency, read_dependencies, dependencies_head, dependency_exists = _readers(DEPENDENCIES)
append_approval, read_approvals, approvals_head, approval_exists = _readers(APPROVALS)
append_metadata, read_metadata, metadata_head, metadata_exists = _readers(METADATA)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def workflow_events(wf) -> list[dict]:
    return [r for r in read_workflow_events() if r.get("workflow_id") == wf]


def workflow_ids() -> list[str]:
    return sorted({r.get("workflow_id") for r in read_workflow_events() if r.get("workflow_id")})


def task_events(tsk) -> list[dict]:
    return [r for r in read_task_events() if r.get("task_id") == tsk]


def task_ids_for(wf) -> list[str]:
    return sorted({r.get("task_id") for r in read_task_events()
                   if r.get("workflow_id") == wf and r.get("task_id")})


def dependencies_for(wf) -> list[dict]:
    return [r for r in read_dependencies() if r.get("workflow_id") == wf]


def approvals_for(wf) -> list[dict]:
    return [r for r in read_approvals() if r.get("workflow_id") == wf]
