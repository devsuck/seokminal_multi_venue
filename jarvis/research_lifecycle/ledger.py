"""Research Lifecycle 원장 (P10.26) — 6개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rl_ 접두사(Research Lifecycle). 각 레코드: id · timestamp · previous_hash · record_hash. 연구
생명주기 추적·기록만 — 실행/배포/승인/거래 없음. 상위 레이어(P10.2~P10.25)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rl_ 접두사)
PROJECTS = ("rl_projects.jsonl", "event_id")              # 이벤트 소싱
EVENTS = ("rl_events.jsonl", "event_id")
TRANSITIONS = ("rl_transitions.jsonl", "transition_id")
BOTTLENECKS = ("rl_bottlenecks.jsonl", "bottleneck_id")
REPORTS = ("rl_reports.jsonl", "report_id")
ARTIFACTS = ("rl_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (PROJECTS, EVENTS, TRANSITIONS, BOTTLENECKS, REPORTS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — P10.2~P10.25. import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "strategy_governance": ("rg_strategies.jsonl", "strategy_id"),
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
    "research_orchestration": ("or_workflows.jsonl", "event_id"),
    "research_observability": ("mh_health_records.jsonl", "health_id"),
    "research_compliance": ("rc_rules.jsonl", "rule_id"),
    "governance_feedback": ("gf_feedback.jsonl", "feedback_id"),
    "governance_memory": ("gm_entries.jsonl", "entry_id"),
    "governance_evolution": ("ge_events.jsonl", "event_id"),
    "governance_orchestration": ("go_layers.jsonl", "event_id"),
    "self_audit_intelligence": ("sa_runs.jsonl", "event_id"),
    "research_risk_intelligence": ("rr_risks.jsonl", "event_id"),
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


# ── Projects (event-sourced) ──
def append_project_event(rec: dict) -> None:
    _append(PROJECTS[0], rec)


def read_project_events() -> list[dict]:
    return read_jsonl(PROJECTS[0])


def projects_head() -> dict | None:
    return _head(PROJECTS[0])


def project_event_exists(event_id: str) -> bool:
    return _exists(PROJECTS[0], PROJECTS[1], event_id)


def project_events_for(project_id: str) -> list[dict]:
    return [r for r in read_project_events() if r.get("project_id") == project_id]


def distinct_projects() -> list[dict]:
    out: dict = {}
    for r in read_project_events():
        pid = r.get("project_id")
        if pid not in out:
            out[pid] = r
    return list(out.values())


def project_exists(project_id: str) -> bool:
    return any(r.get("project_id") == project_id for r in read_project_events())


# ── Lifecycle Events ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(event_id: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], event_id)


def events_for(project_id: str) -> list[dict]:
    return [r for r in read_events() if r.get("project_id") == project_id]


# ── Stage Transitions ──
def append_transition(rec: dict) -> None:
    _append(TRANSITIONS[0], rec)


def read_transitions() -> list[dict]:
    return read_jsonl(TRANSITIONS[0])


def transitions_head() -> dict | None:
    return _head(TRANSITIONS[0])


def transition_exists(transition_id: str) -> bool:
    return _exists(TRANSITIONS[0], TRANSITIONS[1], transition_id)


def transitions_for(project_id: str) -> list[dict]:
    return [r for r in read_transitions() if r.get("project_id") == project_id]


# ── Bottlenecks ──
def append_bottleneck(rec: dict) -> None:
    _append(BOTTLENECKS[0], rec)


def read_bottlenecks() -> list[dict]:
    return read_jsonl(BOTTLENECKS[0])


def bottlenecks_head() -> dict | None:
    return _head(BOTTLENECKS[0])


def bottleneck_exists(bottleneck_id: str) -> bool:
    return _exists(BOTTLENECKS[0], BOTTLENECKS[1], bottleneck_id)


def get_bottleneck(bottleneck_id: str) -> dict | None:
    for r in read_bottlenecks():
        if r.get("bottleneck_id") == bottleneck_id:
            return r
    return None


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
