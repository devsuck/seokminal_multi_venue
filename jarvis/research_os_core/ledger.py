"""Research OS Core 원장 (P10.30) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rosc_ 접두사(Research OS Core). 각 레코드: id · timestamp · previous_hash · record_hash. Phase 10
최종 상위 연구 운영 환경 — 관측·집계·리포트만, 실행/변경 없음. 상위 소스(P9.8~P10.29)는 **READ ONLY** —
파일만 읽고 절대 쓰지 않는다. import 결합 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rosc_ 접두사)
REGISTRY = ("rosc_registry.jsonl", "module_id")      # OS Registry
CATALOG = ("rosc_catalog.jsonl", "catalog_id")       # Module Catalog
STATE = ("rosc_state.jsonl", "state_id")             # Global Research State
SNAPSHOTS = ("rosc_snapshots.jsonl", "snapshot_id")  # System Snapshots
REPORTS = ("rosc_reports.jsonl", "report_id")        # Research Reports

ALL_LEDGERS = (REGISTRY, CATALOG, STATE, SNAPSHOTS, REPORTS)

# ── 모듈 카탈로그(READ ONLY 소스) — 10대 도메인 × 전 계층 P9.8~P10.29. ──
# {domain: [(module_name, filename, id_field, phase)]} — import 결합 없음, 파일만 읽는다.
MODULE_CATALOG = {
    "DATA": [
        ("data_governance", "dg_datasets.jsonl", "dataset_hash", "P9.10"),
        ("research_data", "features.jsonl", "feature_hash", "P9.11"),
    ],
    "MODEL": [
        ("model_governance", "mg_versions.jsonl", "version_id", "P9.12"),
    ],
    "ALPHA": [
        ("alpha_intelligence", "ai_signals.jsonl", "signal_hash", "P10.2"),
        ("research_governance", "rg_strategy_versions.jsonl", "version_id", "P9.8"),
    ],
    "PORTFOLIO": [
        ("portfolio_research", "pr_portfolio_versions.jsonl", "version_id", "P10.3"),
    ],
    "SIMULATION": [
        ("simulation_environment", "sim_runs.jsonl", "event_id", "P10.8"),
    ],
    "DECISION": [
        ("decision_intelligence", "di_frameworks.jsonl", "framework_id", "P10.7"),
        ("causal_intelligence", "ci_variables.jsonl", "variable_id", "P10.4"),
    ],
    "AGENT": [
        ("agent_governance", "arg_agents.jsonl", "event_id", "P9.13"),
        ("self_improvement_intelligence", "si_workflows.jsonl", "workflow_id", "P10.19"),
        ("self_audit_intelligence", "sa_audits.jsonl", "audit_id", "P10.24"),
    ],
    "KNOWLEDGE": [
        ("research_kg", "kg_entities.jsonl", "entity_id", "P10.5"),
        ("knowledge_intelligence", "ki_insights.jsonl", "insight_id", "P10.27"),
        ("research_memory", "rm_lessons.jsonl", "lesson_id", "P10.6"),
        ("governance_memory", "gm_experiences.jsonl", "experience_id", "P10.21"),
    ],
    "AUDIT": [
        ("operational_audit", "audit_events.jsonl", "event_id", "P9.14"),
        ("research_compliance", "rc_checks.jsonl", "check_id", "P10.18"),
        ("research_validation", "rv_sessions.jsonl", "session_id", "P9.9"),
        ("research_risk_intelligence", "rr_assessments.jsonl", "assessment_id", "P10.25"),
    ],
    "CONTROL_PLANE": [
        ("research_control_plane", "rcp_overview.jsonl", "overview_id", "P10.28"),
        ("governance_orchestration", "go_layers.jsonl", "event_id", "P10.23"),
        ("research_orchestration", "or_tasks.jsonl", "event_id", "P10.17"),
        ("research_os", "ros_workflows.jsonl", "event_id", "P10.14"),
        ("research_api", "rapi_endpoints.jsonl", "endpoint_id", "P10.29"),
        ("research_lifecycle", "rl_events.jsonl", "event_id", "P10.26"),
        ("meta_intelligence", "mi_methods.jsonl", "method_id", "P10.9"),
        ("research_evolution", "ev_evolution_cycles.jsonl", "event_id", "P10.10"),
        ("research_planning", "rp_plans.jsonl", "plan_id", "P10.11"),
        ("governance_evolution", "ge_events.jsonl", "event_id", "P10.15"),
        ("governance_feedback", "gf_issues.jsonl", "event_id", "P10.16"),
        ("research_observatory", "ob_metrics.jsonl", "metric_id", "P10.12"),
        ("research_observability", "mh_metrics.jsonl", "metric_id", "P10.13"),
    ],
}


def catalog_modules() -> list:
    """(domain, module, filename, id_field, phase) 평탄 목록(결정적 정렬)."""
    out: list = []
    for domain in sorted(MODULE_CATALOG):
        for module, filename, id_field, phase in MODULE_CATALOG[domain]:
            out.append((domain, module, filename, id_field, phase))
    return out


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


def source_count(filename: str) -> int:
    return len(read_source(filename)) if source_exists(filename) else 0


# ── Registry (OS Registry) ──
def append_module(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_modules() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def module_exists(module_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], module_id)


def get_module(module_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], module_id)


# ── Catalog (Module Catalog) ──
def append_catalog(rec: dict) -> None:
    _append(CATALOG[0], rec)


def read_catalog() -> list[dict]:
    return read_jsonl(CATALOG[0])


def catalog_head() -> dict | None:
    return _head(CATALOG[0])


def catalog_exists(catalog_id: str) -> bool:
    return _exists(CATALOG[0], CATALOG[1], catalog_id)


def get_catalog(catalog_id: str) -> dict | None:
    return _get(CATALOG[0], CATALOG[1], catalog_id)


# ── State (Global Research State) ──
def append_state(rec: dict) -> None:
    _append(STATE[0], rec)


def read_state() -> list[dict]:
    return read_jsonl(STATE[0])


def state_head() -> dict | None:
    return _head(STATE[0])


def state_exists(state_id: str) -> bool:
    return _exists(STATE[0], STATE[1], state_id)


def get_state(state_id: str) -> dict | None:
    return _get(STATE[0], STATE[1], state_id)


# ── Snapshots (System Snapshots) ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


def get_snapshot(snapshot_id: str) -> dict | None:
    return _get(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


# ── Reports (Research Reports) ──
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
