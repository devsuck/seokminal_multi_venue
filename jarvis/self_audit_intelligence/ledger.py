"""Self Audit Intelligence 원장 (P10.24) — 6개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 sa_ 접두사(Self Audit). 각 레코드: id · timestamp · previous_hash · record_hash. 전 생태계 메타
감사·기록만 — 원장/정책/config/permission/strategy/model 수정 없음. 상위 레이어(P9.8~P10.23)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (sa_ 접두사)
AUDITS = ("sa_audits.jsonl", "audit_id")
RUNS = ("sa_runs.jsonl", "event_id")                      # 이벤트 소싱
CHECKS = ("sa_checks.jsonl", "check_id")
VIOLATIONS = ("sa_violations.jsonl", "violation_id")
REPORTS = ("sa_reports.jsonl", "report_id")
ARTIFACTS = ("sa_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (AUDITS, RUNS, CHECKS, VIOLATIONS, REPORTS, ARTIFACTS)

# 감사 대상 상위 원장(READ ONLY) — (파일명, id 필드, kind). kind: chain | event | artifact.
# import 결합 없음, 파일만 읽어 무결성을 검사한다.
AUDIT_TARGETS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_id", "chain"),
    "model_governance": ("mg_models.jsonl", "model_id", "chain"),
    "access_governance": ("ag_operators.jsonl", "identity_hash", "chain"),
    "research_governance": ("rg_strategies.jsonl", "strategy_id", "chain"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id", "chain"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id", "chain"),
    "research_kg": ("kg_entities.jsonl", "entity_id", "chain"),
    "agent_governance": ("arg_agents.jsonl", "agent_id", "chain"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id", "chain"),
    "simulation_environment": ("sim_scenarios.jsonl", "scenario_id", "chain"),
    "research_evolution": ("ev_research_objects.jsonl", "object_id", "chain"),
    "research_evolution_lineage": ("ev_artifacts.jsonl", "artifact_id", "artifact"),
    "research_os": ("ros_layers.jsonl", "event_id", "event"),
    "research_orchestration": ("or_workflows.jsonl", "event_id", "event"),
    "research_observability": ("mh_health_records.jsonl", "health_id", "chain"),
    "research_compliance": ("rc_rules.jsonl", "rule_id", "chain"),
    "research_compliance_lineage": ("rc_artifacts.jsonl", "artifact_id", "artifact"),
    "governance_feedback": ("gf_feedback.jsonl", "feedback_id", "chain"),
    "governance_memory": ("gm_entries.jsonl", "entry_id", "chain"),
    "governance_evolution": ("ge_events.jsonl", "event_id", "chain"),
    "governance_evolution_states": ("ge_states.jsonl", "event_id", "event"),
    "governance_orchestration": ("go_layers.jsonl", "event_id", "event"),
    "governance_orchestration_lineage": ("go_artifacts.jsonl", "artifact_id", "artifact"),
}

# 존재가 기대되는 핵심 거버넌스 계층(누락 검증 탐지용)
EXPECTED_GOVERNANCE_LAYERS = (
    "data_governance", "model_governance", "access_governance", "research_compliance",
    "governance_feedback", "governance_memory", "governance_evolution",
    "governance_orchestration",
)


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


# ── 감사 대상 상위 원장 READ ONLY 로드 ──
def read_target(filename: str) -> list[dict]:
    """감사 대상 상위 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def target_exists(layer: str) -> bool:
    spec = AUDIT_TARGETS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def target_count(layer: str) -> int:
    spec = AUDIT_TARGETS.get(layer)
    if not spec:
        return 0
    return len(read_target(spec[0]))


# ── Audits (불변 정의) ──
def append_audit(rec: dict) -> None:
    _append(AUDITS[0], rec)


def read_audits() -> list[dict]:
    return read_jsonl(AUDITS[0])


def audits_head() -> dict | None:
    return _head(AUDITS[0])


def audit_exists(audit_id: str) -> bool:
    return _exists(AUDITS[0], AUDITS[1], audit_id)


def get_audit(audit_id: str) -> dict | None:
    for r in read_audits():
        if r.get("audit_id") == audit_id:
            return r
    return None


# ── Runs (event-sourced) ──
def append_run_event(rec: dict) -> None:
    _append(RUNS[0], rec)


def read_run_events() -> list[dict]:
    return read_jsonl(RUNS[0])


def runs_head() -> dict | None:
    return _head(RUNS[0])


def run_event_exists(event_id: str) -> bool:
    return _exists(RUNS[0], RUNS[1], event_id)


def run_events_for(run_id: str) -> list[dict]:
    return [r for r in read_run_events() if r.get("run_id") == run_id]


def distinct_runs() -> list[dict]:
    out: dict = {}
    for r in read_run_events():
        rid = r.get("run_id")
        if rid not in out:
            out[rid] = r
    return list(out.values())


def run_exists(run_id: str) -> bool:
    return any(r.get("run_id") == run_id for r in read_run_events())


# ── Checks (불변) ──
def append_check(rec: dict) -> None:
    _append(CHECKS[0], rec)


def read_checks() -> list[dict]:
    return read_jsonl(CHECKS[0])


def checks_head() -> dict | None:
    return _head(CHECKS[0])


def check_exists(check_id: str) -> bool:
    return _exists(CHECKS[0], CHECKS[1], check_id)


def checks_for(run_ref: str) -> list[dict]:
    return [r for r in read_checks() if r.get("run_ref") == run_ref]


# ── Violations (불변) ──
def append_violation(rec: dict) -> None:
    _append(VIOLATIONS[0], rec)


def read_violations() -> list[dict]:
    return read_jsonl(VIOLATIONS[0])


def violations_head() -> dict | None:
    return _head(VIOLATIONS[0])


def violation_exists(violation_id: str) -> bool:
    return _exists(VIOLATIONS[0], VIOLATIONS[1], violation_id)


def violations_for(run_ref: str) -> list[dict]:
    return [r for r in read_violations() if r.get("run_ref") == run_ref]


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
