"""Autonomous Research Organization 원장 (P11.13) — 10개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rorg_ 접두사(Research ORGanization). 각 레코드: id · timestamp · previous_hash · record_hash. 조직 조정
기록만 — 실행/배포/승인/자본 배분/모델·전략 수정/권한 변경 없음. 상위 계층(P9.8/P9.9, P10.1~P10.8, P11.1~P11.12)은
**READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rorg_ 접두사)
ORGANIZATIONS = ("rorg_organizations.jsonl", "org_event_id")   # Research Organization Registry(event-sourced)
UNITS = ("rorg_units.jsonl", "unit_id")                        # Research Units
TEAMS = ("rorg_teams.jsonl", "team_id")                        # Research Teams
ROLES = ("rorg_roles.jsonl", "role_id")                        # Agent Roles
RESPONSIBILITIES = ("rorg_responsibilities.jsonl", "responsibility_id")  # Research Responsibilities
WORKFLOWS = ("rorg_workflows.jsonl", "workflow_id")            # Workflow Ownership Records
POLICIES = ("rorg_policies.jsonl", "policy_id")                # Coordination Policies
SNAPSHOTS = ("rorg_snapshots.jsonl", "snapshot_id")            # Organization Snapshots
REPORTS = ("rorg_reports.jsonl", "report_id")                  # Organization Reports
ARTIFACTS = ("rorg_artifacts.jsonl", "artifact_id")           # Artifact Lineage

ALL_LEDGERS = (ORGANIZATIONS, UNITS, TEAMS, ROLES, RESPONSIBILITIES, WORKFLOWS, POLICIES,
               SNAPSHOTS, REPORTS, ARTIFACTS)

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


# ── Organizations (event-sourced) ──
def append_org_event(rec: dict) -> None:
    _append(ORGANIZATIONS[0], rec)


def read_org_events() -> list[dict]:
    return read_jsonl(ORGANIZATIONS[0])


def organizations_head() -> dict | None:
    return _head(ORGANIZATIONS[0])


def org_event_exists(org_event_id: str) -> bool:
    return _exists(ORGANIZATIONS[0], ORGANIZATIONS[1], org_event_id)


def org_events(org_id: str) -> list[dict]:
    return [r for r in read_org_events() if r.get("org_id") == org_id]


def org_ids() -> list[str]:
    return sorted({r.get("org_id") for r in read_org_events() if r.get("org_id")})


# ── Units ──
def append_unit(rec: dict) -> None:
    _append(UNITS[0], rec)


def read_units() -> list[dict]:
    return read_jsonl(UNITS[0])


def units_head() -> dict | None:
    return _head(UNITS[0])


def unit_exists(unit_id: str) -> bool:
    return _exists(UNITS[0], UNITS[1], unit_id)


def get_unit(unit_id: str) -> dict | None:
    return _get(UNITS[0], UNITS[1], unit_id)


def org_units(org_id: str) -> list[dict]:
    return [r for r in read_units() if r.get("org_id") == org_id]


# ── Teams ──
def append_team(rec: dict) -> None:
    _append(TEAMS[0], rec)


def read_teams() -> list[dict]:
    return read_jsonl(TEAMS[0])


def teams_head() -> dict | None:
    return _head(TEAMS[0])


def team_exists(team_id: str) -> bool:
    return _exists(TEAMS[0], TEAMS[1], team_id)


def get_team(team_id: str) -> dict | None:
    return _get(TEAMS[0], TEAMS[1], team_id)


def unit_teams(unit_id: str) -> list[dict]:
    return [r for r in read_teams() if r.get("unit_id") == unit_id]


# ── Roles ──
def append_role(rec: dict) -> None:
    _append(ROLES[0], rec)


def read_roles() -> list[dict]:
    return read_jsonl(ROLES[0])


def roles_head() -> dict | None:
    return _head(ROLES[0])


def role_exists(role_id: str) -> bool:
    return _exists(ROLES[0], ROLES[1], role_id)


def get_role(role_id: str) -> dict | None:
    return _get(ROLES[0], ROLES[1], role_id)


def unit_roles(unit_id: str) -> list[dict]:
    return [r for r in read_roles() if r.get("unit_id") == unit_id]


# ── Responsibilities ──
def append_responsibility(rec: dict) -> None:
    _append(RESPONSIBILITIES[0], rec)


def read_responsibilities() -> list[dict]:
    return read_jsonl(RESPONSIBILITIES[0])


def responsibilities_head() -> dict | None:
    return _head(RESPONSIBILITIES[0])


def responsibility_exists(responsibility_id: str) -> bool:
    return _exists(RESPONSIBILITIES[0], RESPONSIBILITIES[1], responsibility_id)


def get_responsibility(responsibility_id: str) -> dict | None:
    return _get(RESPONSIBILITIES[0], RESPONSIBILITIES[1], responsibility_id)


def org_responsibilities(org_id: str) -> list[dict]:
    return [r for r in read_responsibilities() if r.get("org_id") == org_id]


# ── Workflows ──
def append_workflow(rec: dict) -> None:
    _append(WORKFLOWS[0], rec)


def read_workflows() -> list[dict]:
    return read_jsonl(WORKFLOWS[0])


def workflows_head() -> dict | None:
    return _head(WORKFLOWS[0])


def workflow_exists(workflow_id: str) -> bool:
    return _exists(WORKFLOWS[0], WORKFLOWS[1], workflow_id)


def get_workflow(workflow_id: str) -> dict | None:
    return _get(WORKFLOWS[0], WORKFLOWS[1], workflow_id)


def org_workflows(org_id: str) -> list[dict]:
    return [r for r in read_workflows() if r.get("org_id") == org_id]


# ── Policies ──
def append_policy(rec: dict) -> None:
    _append(POLICIES[0], rec)


def read_policies() -> list[dict]:
    return read_jsonl(POLICIES[0])


def policies_head() -> dict | None:
    return _head(POLICIES[0])


def policy_exists(policy_id: str) -> bool:
    return _exists(POLICIES[0], POLICIES[1], policy_id)


def org_policies(org_id: str) -> list[dict]:
    return [r for r in read_policies() if r.get("org_id") == org_id]


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


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
