"""Autonomous Experiment Scheduler 원장 (P12.2) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 aes_ 접두사(Autonomous Experiment Scheduler). 각 레코드: id · timestamp · previous_hash · record_hash.
스케줄링 기록만 — 실험 실행 없음. 상위 계층(P9.8~P12.1)은 **READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (aes_ 접두사)
REGISTRY = ("aes_registry.jsonl", "schedule_id")             # Experiment Queue Registry
SCHEDULES = ("aes_schedules.jsonl", "schedule_event_id")     # Experiment Schedule Records(event-sourced)
POLICIES = ("aes_policies.jsonl", "policy_id")               # Scheduling Policies
PRIORITIES = ("aes_priorities.jsonl", "priority_id")         # Priority Rules
DEPENDENCIES = ("aes_dependencies.jsonl", "dependency_id")   # Dependency Graph
SNAPSHOTS = ("aes_snapshots.jsonl", "snapshot_id")           # Schedule Snapshots
REPORTS = ("aes_reports.jsonl", "report_id")                 # Scheduling Reports

ALL_LEDGERS = (REGISTRY, SCHEDULES, POLICIES, PRIORITIES, DEPENDENCIES, SNAPSHOTS, REPORTS)

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
    "experiment_manager": ("exm_experiments.jsonl", "event_id"),             # P11.4
    "research_conflict_resolution": ("crf_outcomes.jsonl", "resolution_id"),  # P11.9
    "research_event_bus": ("reb_events.jsonl", "event_lifecycle_id"),        # P11.11
    "research_organization": ("rorg_organizations.jsonl", "org_event_id"),   # P11.13
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
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
def append_schedule(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_schedules() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def schedule_exists(schedule_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], schedule_id)


def get_schedule(schedule_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], schedule_id)


# ── Schedule Records (event-sourced request lifecycle) ──
def append_schedule_event(rec: dict) -> None:
    _append(SCHEDULES[0], rec)


def read_schedule_events() -> list[dict]:
    return read_jsonl(SCHEDULES[0])


def schedules_head() -> dict | None:
    return _head(SCHEDULES[0])


def schedule_event_exists(schedule_event_id: str) -> bool:
    return _exists(SCHEDULES[0], SCHEDULES[1], schedule_event_id)


def request_events(request_id: str) -> list[dict]:
    return [r for r in read_schedule_events() if r.get("request_id") == request_id]


def request_ids() -> list[str]:
    return sorted({r.get("request_id") for r in read_schedule_events() if r.get("request_id")})


def schedule_requests(schedule_id: str) -> list[str]:
    return sorted({r.get("request_id") for r in read_schedule_events()
                   if r.get("schedule_id") == schedule_id and r.get("request_id")})


# ── Policies ──
def append_policy(rec: dict) -> None:
    _append(POLICIES[0], rec)


def read_policies() -> list[dict]:
    return read_jsonl(POLICIES[0])


def policies_head() -> dict | None:
    return _head(POLICIES[0])


def policy_exists(policy_id: str) -> bool:
    return _exists(POLICIES[0], POLICIES[1], policy_id)


def schedule_policies(schedule_id: str) -> list[dict]:
    return [r for r in read_policies() if r.get("schedule_id") == schedule_id]


# ── Priorities ──
def append_priority(rec: dict) -> None:
    _append(PRIORITIES[0], rec)


def read_priorities() -> list[dict]:
    return read_jsonl(PRIORITIES[0])


def priorities_head() -> dict | None:
    return _head(PRIORITIES[0])


def priority_exists(priority_id: str) -> bool:
    return _exists(PRIORITIES[0], PRIORITIES[1], priority_id)


def get_priority(priority_id: str) -> dict | None:
    return _get(PRIORITIES[0], PRIORITIES[1], priority_id)


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


def request_dependencies(request_id: str) -> list[dict]:
    return [r for r in read_dependencies() if r.get("request_id") == request_id]


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)
