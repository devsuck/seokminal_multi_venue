"""Research Control Plane 원장 (P10.28) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rcp_ 접두사(Research Control Plane). 각 레코드: id · timestamp · previous_hash · record_hash. 중앙
관측·조율 평면 — 관측·집계·리포트만, 실행/변경 없음. 상위 소스(P9.8~P10.27)는 **READ ONLY** — 파일만 읽고
절대 쓰지 않는다. import 결합 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rcp_ 접두사)
COMPONENTS = ("rcp_components.jsonl", "component_id")
STATUS = ("rcp_status.jsonl", "status_id")
DEPENDENCIES = ("rcp_dependencies.jsonl", "dependency_id")
OVERVIEW = ("rcp_overview.jsonl", "overview_id")
DASHBOARD = ("rcp_dashboard.jsonl", "dashboard_id")
TIMELINE = ("rcp_timeline.jsonl", "event_id")
HEALTH = ("rcp_health.jsonl", "health_id")
REPORTS = ("rcp_reports.jsonl", "report_id")

ALL_LEDGERS = (COMPONENTS, STATUS, DEPENDENCIES, OVERVIEW, DASHBOARD, TIMELINE, HEALTH, REPORTS)

# ── 상위 소스 원장(READ ONLY) — Research OS 전 계층 P9.8~P10.27. ──
# {component_name: (filename, id_field, phase, category)} — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategy_versions.jsonl", "version_id", "P9.8", "RESEARCH"),
    "research_validation": ("rv_sessions.jsonl", "session_id", "P9.9", "RESEARCH"),
    "research_data": ("features.jsonl", "feature_hash", "P9.10", "RESEARCH"),
    "research_kg": ("kg_entities.jsonl", "entity_id", "P10.5", "INTELLIGENCE"),
    "research_memory": ("rm_lessons.jsonl", "lesson_id", "P10.6", "INTELLIGENCE"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash", "P10.2", "RESEARCH"),
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id", "P10.3", "RESEARCH"),
    "causal_intelligence": ("ci_variables.jsonl", "variable_id", "P10.4", "INTELLIGENCE"),
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id", "P10.7", "INTELLIGENCE"),
    "simulation_environment": ("sim_runs.jsonl", "event_id", "P10.8", "RESEARCH"),
    "meta_intelligence": ("mi_methods.jsonl", "method_id", "P10.9", "INTELLIGENCE"),
    "research_evolution": ("ev_evolution_cycles.jsonl", "event_id", "P10.10", "RESEARCH"),
    "research_planning": ("rp_plans.jsonl", "plan_id", "P10.11", "RESEARCH"),
    "research_orchestration": ("or_tasks.jsonl", "event_id", "P10.17", "GOVERNANCE"),
    "research_observatory": ("ob_metrics.jsonl", "metric_id", "P10.12", "OBSERVABILITY"),
    "research_observability": ("mh_metrics.jsonl", "metric_id", "P10.13", "OBSERVABILITY"),
    "research_os": ("ros_workflows.jsonl", "event_id", "P10.14", "GOVERNANCE"),
    "governance_evolution": ("ge_events.jsonl", "event_id", "P10.15", "GOVERNANCE"),
    "governance_feedback": ("gf_issues.jsonl", "event_id", "P10.16", "GOVERNANCE"),
    "governance_memory": ("gm_experiences.jsonl", "experience_id", "P10.21", "GOVERNANCE"),
    "governance_orchestration": ("go_layers.jsonl", "event_id", "P10.23", "GOVERNANCE"),
    "research_compliance": ("rc_checks.jsonl", "check_id", "P10.18", "GOVERNANCE"),
    "self_audit_intelligence": ("sa_audits.jsonl", "audit_id", "P10.24", "INTELLIGENCE"),
    "self_improvement_intelligence": ("si_workflows.jsonl", "workflow_id", "P10.19", "INTELLIGENCE"),
    "research_risk_intelligence": ("rr_assessments.jsonl", "assessment_id", "P10.25", "INTELLIGENCE"),
    "research_lifecycle": ("rl_events.jsonl", "event_id", "P10.26", "RESEARCH"),
    "knowledge_intelligence": ("ki_insights.jsonl", "insight_id", "P10.27", "INTELLIGENCE"),
}

# 타임스탬프 후보 필드(상위 소스 마지막 활동 추정, READ ONLY).
_TS_FIELDS = ("created_at", "occurred_at", "recorded_at", "timestamp", "observed_at",
              "generated_at", "computed_at", "registered_at")


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
def source_exists(filename: str) -> bool:
    return os.path.exists(state_path(filename))


def read_source(filename: str) -> list[dict]:
    """상위 소스 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def source_last_activity(records: list[dict]) -> str:
    ts = ""
    for r in records:
        for f in _TS_FIELDS:
            v = r.get(f)
            if v and str(v) > ts:
                ts = str(v)
                break
    return ts


# ── Components ──
def append_component(rec: dict) -> None:
    _append(COMPONENTS[0], rec)


def read_components() -> list[dict]:
    return read_jsonl(COMPONENTS[0])


def components_head() -> dict | None:
    return _head(COMPONENTS[0])


def component_exists(component_id: str) -> bool:
    return _exists(COMPONENTS[0], COMPONENTS[1], component_id)


def get_component(component_id: str) -> dict | None:
    return _get(COMPONENTS[0], COMPONENTS[1], component_id)


# ── Layer Status ──
def append_status(rec: dict) -> None:
    _append(STATUS[0], rec)


def read_status() -> list[dict]:
    return read_jsonl(STATUS[0])


def status_head() -> dict | None:
    return _head(STATUS[0])


def status_exists(status_id: str) -> bool:
    return _exists(STATUS[0], STATUS[1], status_id)


def get_status(status_id: str) -> dict | None:
    return _get(STATUS[0], STATUS[1], status_id)


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


# ── System Overview ──
def append_overview(rec: dict) -> None:
    _append(OVERVIEW[0], rec)


def read_overview() -> list[dict]:
    return read_jsonl(OVERVIEW[0])


def overview_head() -> dict | None:
    return _head(OVERVIEW[0])


def overview_exists(overview_id: str) -> bool:
    return _exists(OVERVIEW[0], OVERVIEW[1], overview_id)


def get_overview(overview_id: str) -> dict | None:
    return _get(OVERVIEW[0], OVERVIEW[1], overview_id)


# ── Governance Dashboard ──
def append_dashboard(rec: dict) -> None:
    _append(DASHBOARD[0], rec)


def read_dashboard() -> list[dict]:
    return read_jsonl(DASHBOARD[0])


def dashboard_head() -> dict | None:
    return _head(DASHBOARD[0])


def dashboard_exists(dashboard_id: str) -> bool:
    return _exists(DASHBOARD[0], DASHBOARD[1], dashboard_id)


def get_dashboard(dashboard_id: str) -> dict | None:
    return _get(DASHBOARD[0], DASHBOARD[1], dashboard_id)


# ── Research Timeline ──
def append_timeline(rec: dict) -> None:
    _append(TIMELINE[0], rec)


def read_timeline() -> list[dict]:
    return read_jsonl(TIMELINE[0])


def timeline_head() -> dict | None:
    return _head(TIMELINE[0])


def timeline_exists(event_id: str) -> bool:
    return _exists(TIMELINE[0], TIMELINE[1], event_id)


# ── Health Metrics ──
def append_health(rec: dict) -> None:
    _append(HEALTH[0], rec)


def read_health() -> list[dict]:
    return read_jsonl(HEALTH[0])


def health_head() -> dict | None:
    return _head(HEALTH[0])


def health_exists(health_id: str) -> bool:
    return _exists(HEALTH[0], HEALTH[1], health_id)


def get_health(health_id: str) -> dict | None:
    return _get(HEALTH[0], HEALTH[1], health_id)


# ── Control Reports ──
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
