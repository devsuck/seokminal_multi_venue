"""Research Orchestration 원장 (P10.17) — 9개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 or_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 연구 과정 가시성·조정
기록만 — 실행/거래/배포/config 변경/자동 트리거 없음. 상위 레이어(P9.8~P10.16)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (or_ 접두사)
WORKFLOWS = ("or_workflows.jsonl", "event_id")            # 이벤트 소싱
PIPELINES = ("or_pipeline_versions.jsonl", "pipeline_id")
TASKS = ("or_tasks.jsonl", "event_id")                    # 이벤트 소싱
DEPENDENCIES = ("or_dependencies.jsonl", "dependency_id")
RUNS = ("or_runs.jsonl", "run_id")
EVENTS = ("or_events.jsonl", "event_id")
BOTTLENECKS = ("or_bottlenecks.jsonl", "event_id")        # 이벤트 소싱
REPORTS = ("or_reports.jsonl", "report_id")
ARTIFACTS = ("or_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (WORKFLOWS, PIPELINES, TASKS, DEPENDENCIES, RUNS, EVENTS, BOTTLENECKS, REPORTS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
# 논리 레이어명 -> (대표 원장 파일명, id 필드)
SOURCE_LEDGERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_id"),
    "model_governance": ("mg_models.jsonl", "model_id"),
    "access_governance": ("ag_operators.jsonl", "identity_hash"),
    "research_data": ("datasets.jsonl", "dataset_id"),
    "research_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "agent_governance": ("arg_agents.jsonl", "agent_id"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id"),
    "simulation_environment": ("sim_scenarios.jsonl", "scenario_id"),
    "research_validation": ("rv_validations.jsonl", "event_id"),
    "research_observatory": ("ob_snapshots.jsonl", "event_id"),
    "causal_intelligence": ("ci_hypotheses.jsonl", "event_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_opportunities.jsonl", "event_id"),
    "research_memory": ("rm_memories.jsonl", "event_id"),
    "research_planning": ("rp_opportunities.jsonl", "event_id"),
    "research_evolution": ("ev_research_objects.jsonl", "object_id"),
    "research_os": ("ros_layers.jsonl", "event_id"),
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


# ── 상위 레이어 READ ONLY 소스 ──
def read_source(filename: str) -> list[dict]:
    """상위 레이어 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def source_count(layer: str) -> int:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return 0
    return len(read_source(spec[0]))


# ── Workflows (event-sourced) ──
def append_workflow_event(rec: dict) -> None:
    _append(WORKFLOWS[0], rec)


def read_workflow_events() -> list[dict]:
    return read_jsonl(WORKFLOWS[0])


def workflows_head() -> dict | None:
    return _head(WORKFLOWS[0])


def workflow_event_exists(event_id: str) -> bool:
    return _exists(WORKFLOWS[0], WORKFLOWS[1], event_id)


def workflow_events_for(workflow_id: str) -> list[dict]:
    return [r for r in read_workflow_events() if r.get("workflow_id") == workflow_id]


def distinct_workflows() -> list[dict]:
    out: dict = {}
    for r in read_workflow_events():
        wid = r.get("workflow_id")
        if wid not in out:
            out[wid] = r
    return list(out.values())


def workflow_exists(workflow_id: str) -> bool:
    return any(r.get("workflow_id") == workflow_id for r in read_workflow_events())


# ── Pipelines (immutable) ──
def append_pipeline(rec: dict) -> None:
    _append(PIPELINES[0], rec)


def read_pipelines() -> list[dict]:
    return read_jsonl(PIPELINES[0])


def pipelines_head() -> dict | None:
    return _head(PIPELINES[0])


def pipeline_exists(pipeline_id: str) -> bool:
    return _exists(PIPELINES[0], PIPELINES[1], pipeline_id)


def get_pipeline(pipeline_id: str) -> dict | None:
    for r in read_pipelines():
        if r.get("pipeline_id") == pipeline_id:
            return r
    return None


def pipelines_for(workflow_id: str) -> list[dict]:
    return [r for r in read_pipelines() if r.get("workflow_id") == workflow_id]


# ── Tasks (event-sourced) ──
def append_task_event(rec: dict) -> None:
    _append(TASKS[0], rec)


def read_task_events() -> list[dict]:
    return read_jsonl(TASKS[0])


def tasks_head() -> dict | None:
    return _head(TASKS[0])


def task_event_exists(event_id: str) -> bool:
    return _exists(TASKS[0], TASKS[1], event_id)


def task_events_for(task_id: str) -> list[dict]:
    return [r for r in read_task_events() if r.get("task_id") == task_id]


def distinct_tasks() -> list[dict]:
    out: dict = {}
    for r in read_task_events():
        tid = r.get("task_id")
        if tid not in out:
            out[tid] = r
    return list(out.values())


def task_exists(task_id: str) -> bool:
    return any(r.get("task_id") == task_id for r in read_task_events())


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


# ── Runs ──
def append_run(rec: dict) -> None:
    _append(RUNS[0], rec)


def read_runs() -> list[dict]:
    return read_jsonl(RUNS[0])


def runs_head() -> dict | None:
    return _head(RUNS[0])


def run_exists(run_id: str) -> bool:
    return _exists(RUNS[0], RUNS[1], run_id)


def runs_for(workflow_id: str) -> list[dict]:
    return [r for r in read_runs() if r.get("workflow_id") == workflow_id]


# ── Events ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(event_id: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], event_id)


# ── Bottlenecks (event-sourced) ──
def append_bottleneck_event(rec: dict) -> None:
    _append(BOTTLENECKS[0], rec)


def read_bottleneck_events() -> list[dict]:
    return read_jsonl(BOTTLENECKS[0])


def bottlenecks_head() -> dict | None:
    return _head(BOTTLENECKS[0])


def bottleneck_event_exists(event_id: str) -> bool:
    return _exists(BOTTLENECKS[0], BOTTLENECKS[1], event_id)


def bottleneck_events_for(bottleneck_id: str) -> list[dict]:
    return [r for r in read_bottleneck_events() if r.get("bottleneck_id") == bottleneck_id]


def distinct_bottlenecks() -> list[dict]:
    out: dict = {}
    for r in read_bottleneck_events():
        bid = r.get("bottleneck_id")
        if bid not in out:
            out[bid] = r
    return list(out.values())


def bottleneck_exists(bottleneck_id: str) -> bool:
    return any(r.get("bottleneck_id") == bottleneck_id for r in read_bottleneck_events())


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (계보) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
