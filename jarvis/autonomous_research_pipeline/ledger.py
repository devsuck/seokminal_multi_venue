"""Autonomous Research Pipeline 원장 (P12.1) — 9개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 arp_ 접두사(Autonomous Research Pipeline). 각 레코드: id · timestamp · previous_hash · record_hash.
파이프라인 오케스트레이션 기록만 — 거래 실행/전략 배포/자본 배분/라이브 수정/모델 승인/권한 변경 없음. 상위 계층
(P9.8/P9.9, P10.1~P10.8, P11.1~P11.13)은 **READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (arp_ 접두사)
REGISTRY = ("arp_registry.jsonl", "pipeline_id")             # Research Pipeline Registry
OBJECTIVES = ("arp_objectives.jsonl", "objective_id")        # Research Objectives
CYCLES = ("arp_cycles.jsonl", "cycle_id")                    # Research Cycles
RUNS = ("arp_runs.jsonl", "run_id")                          # Pipeline Runs
STAGES = ("arp_stages.jsonl", "stage_id")                    # Workflow Stages
TRANSITIONS = ("arp_transitions.jsonl", "transition_event_id")  # Stage Transitions (event-sourced)
ARTIFACTS = ("arp_artifacts.jsonl", "artifact_id")           # Pipeline Artifacts
REPORTS = ("arp_reports.jsonl", "report_id")                 # Pipeline Reports
HISTORY = ("arp_history.jsonl", "history_id")                # Execution History Records

ALL_LEDGERS = (REGISTRY, OBJECTIVES, CYCLES, RUNS, STAGES, TRANSITIONS, ARTIFACTS, REPORTS, HISTORY)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_hash"),                 # P9.8
    "model_governance": ("mg_models.jsonl", "model_hash"),                   # P9.9
    "research_data": ("datasets.jsonl", "dataset_hash"),                     # P10.1
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),      # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),               # P10.3
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id"),      # P10.4
    "research_kg": ("kg_entities.jsonl", "entity_id"),                       # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "simulation_environment": ("sim_runs.jsonl", "event_id"),                # P10.8
    "research_agents": ("ragt_reports.jsonl", "report_id"),                  # P11.1
    "research_task_planner": ("rtp_tasks.jsonl", "task_id"),                 # P11.2
    "research_literature": ("rli_papers.jsonl", "paper_id"),                 # P11.3
    "experiment_manager": ("exm_experiments.jsonl", "event_id"),             # P11.4
    "research_reviewer": ("rvw_reviews.jsonl", "review_id"),                 # P11.5
    "research_council": ("cnl_consensus.jsonl", "consensus_id"),             # P11.6
    "research_coordinator": ("rco_reports.jsonl", "report_id"),              # P11.7
    "knowledge_sharing": ("ksh_entries.jsonl", "entry_id"),                  # P11.8
    "research_conflict_resolution": ("crf_outcomes.jsonl", "resolution_id"),  # P11.9
    "research_improvement": ("rimp_registry.jsonl", "registry_id"),          # P11.10
    "research_event_bus": ("reb_events.jsonl", "event_lifecycle_id"),        # P11.11
    "research_memory_system": ("rmem_registry.jsonl", "registry_id"),        # P11.12
    "research_organization": ("rorg_organizations.jsonl", "org_event_id"),   # P11.13
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


# ── Registry ──
def append_pipeline(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_pipelines() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def pipeline_exists(pipeline_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], pipeline_id)


def get_pipeline(pipeline_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], pipeline_id)


# ── Objectives ──
def append_objective(rec: dict) -> None:
    _append(OBJECTIVES[0], rec)


def read_objectives() -> list[dict]:
    return read_jsonl(OBJECTIVES[0])


def objectives_head() -> dict | None:
    return _head(OBJECTIVES[0])


def objective_exists(objective_id: str) -> bool:
    return _exists(OBJECTIVES[0], OBJECTIVES[1], objective_id)


def get_objective(objective_id: str) -> dict | None:
    return _get(OBJECTIVES[0], OBJECTIVES[1], objective_id)


# ── Cycles ──
def append_cycle(rec: dict) -> None:
    _append(CYCLES[0], rec)


def read_cycles() -> list[dict]:
    return read_jsonl(CYCLES[0])


def cycles_head() -> dict | None:
    return _head(CYCLES[0])


def cycle_exists(cycle_id: str) -> bool:
    return _exists(CYCLES[0], CYCLES[1], cycle_id)


def get_cycle(cycle_id: str) -> dict | None:
    return _get(CYCLES[0], CYCLES[1], cycle_id)


def cycle_ids() -> list[str]:
    return sorted(r.get("cycle_id") for r in read_cycles() if r.get("cycle_id"))


# ── Runs ──
def append_run(rec: dict) -> None:
    _append(RUNS[0], rec)


def read_runs() -> list[dict]:
    return read_jsonl(RUNS[0])


def runs_head() -> dict | None:
    return _head(RUNS[0])


def run_exists(run_id: str) -> bool:
    return _exists(RUNS[0], RUNS[1], run_id)


def cycle_runs(cycle_id: str) -> list[dict]:
    return [r for r in read_runs() if r.get("cycle_id") == cycle_id]


# ── Stages ──
def append_stage(rec: dict) -> None:
    _append(STAGES[0], rec)


def read_stages() -> list[dict]:
    return read_jsonl(STAGES[0])


def stages_head() -> dict | None:
    return _head(STAGES[0])


def stage_exists(stage_id: str) -> bool:
    return _exists(STAGES[0], STAGES[1], stage_id)


def cycle_stages(cycle_id: str) -> list[dict]:
    return [r for r in read_stages() if r.get("cycle_id") == cycle_id]


# ── Transitions (event-sourced) ──
def append_transition(rec: dict) -> None:
    _append(TRANSITIONS[0], rec)


def read_transitions() -> list[dict]:
    return read_jsonl(TRANSITIONS[0])


def transitions_head() -> dict | None:
    return _head(TRANSITIONS[0])


def transition_exists(transition_event_id: str) -> bool:
    return _exists(TRANSITIONS[0], TRANSITIONS[1], transition_event_id)


def cycle_transitions(cycle_id: str) -> list[dict]:
    return [r for r in read_transitions() if r.get("cycle_id") == cycle_id]


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── History ──
def append_history(rec: dict) -> None:
    _append(HISTORY[0], rec)


def read_history() -> list[dict]:
    return read_jsonl(HISTORY[0])


def history_head() -> dict | None:
    return _head(HISTORY[0])


def history_exists(history_id: str) -> bool:
    return _exists(HISTORY[0], HISTORY[1], history_id)


def cycle_history(cycle_id: str) -> list[dict]:
    return [r for r in read_history() if r.get("cycle_id") == cycle_id]
