"""Governance Evolution 원장 (P10.22) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ge_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 거버넌스 진화 관찰·분석·
기록만 — 규칙 수정·업그레이드 적용·config 변경·배포 없음. 상위 레이어(P9.8~P10.21)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ge_ 접두사)
EVENTS = ("ge_events.jsonl", "event_id")
STATES = ("ge_states.jsonl", "event_id")                  # 이벤트 소싱(타임라인)
MATURITY = ("ge_maturity.jsonl", "assessment_id")
PATTERNS = ("ge_patterns.jsonl", "pattern_id")
COMPARISONS = ("ge_comparisons.jsonl", "comparison_id")
SNAPSHOTS = ("ge_snapshots.jsonl", "snapshot_id")
REPORTS = ("ge_reports.jsonl", "report_id")
ARTIFACTS = ("ge_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (EVENTS, STATES, MATURITY, PATTERNS, COMPARISONS, SNAPSHOTS, REPORTS, ARTIFACTS)

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
    "research_orchestration": ("or_workflows.jsonl", "event_id"),
    "research_observability": ("mh_health_records.jsonl", "health_id"),
    "research_compliance": ("rc_rules.jsonl", "rule_id"),
    "governance_feedback": ("gf_feedback.jsonl", "feedback_id"),
    "governance_memory": ("gm_entries.jsonl", "entry_id"),
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


# ── Events (불변) ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(event_id: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], event_id)


def get_event(event_id: str) -> dict | None:
    for r in read_events():
        if r.get("event_id") == event_id:
            return r
    return None


# ── States (event-sourced 타임라인) ──
def append_state_event(rec: dict) -> None:
    _append(STATES[0], rec)


def read_state_events() -> list[dict]:
    return read_jsonl(STATES[0])


def states_head() -> dict | None:
    return _head(STATES[0])


def state_event_exists(event_id: str) -> bool:
    return _exists(STATES[0], STATES[1], event_id)


def state_events_for(state_id: str) -> list[dict]:
    return [r for r in read_state_events() if r.get("state_id") == state_id]


def get_state_event(event_id: str) -> dict | None:
    for r in read_state_events():
        if r.get("event_id") == event_id:
            return r
    return None


def distinct_states() -> list[dict]:
    out: dict = {}
    for r in read_state_events():
        sid = r.get("state_id")
        out[sid] = r  # 마지막(최신) 상태 유지
    return list(out.values())


# ── Maturity (불변) ──
def append_maturity(rec: dict) -> None:
    _append(MATURITY[0], rec)


def read_maturity() -> list[dict]:
    return read_jsonl(MATURITY[0])


def maturity_head() -> dict | None:
    return _head(MATURITY[0])


def maturity_exists(assessment_id: str) -> bool:
    return _exists(MATURITY[0], MATURITY[1], assessment_id)


def get_maturity(assessment_id: str) -> dict | None:
    for r in read_maturity():
        if r.get("assessment_id") == assessment_id:
            return r
    return None


# ── Patterns (불변) ──
def append_pattern(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_patterns() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_exists(pattern_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], pattern_id)


def get_pattern(pattern_id: str) -> dict | None:
    for r in read_patterns():
        if r.get("pattern_id") == pattern_id:
            return r
    return None


# ── Comparisons (불변) ──
def append_comparison(rec: dict) -> None:
    _append(COMPARISONS[0], rec)


def read_comparisons() -> list[dict]:
    return read_jsonl(COMPARISONS[0])


def comparisons_head() -> dict | None:
    return _head(COMPARISONS[0])


def comparison_exists(comparison_id: str) -> bool:
    return _exists(COMPARISONS[0], COMPARISONS[1], comparison_id)


# ── Snapshots (불변) ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


def get_snapshot(snapshot_id: str) -> dict | None:
    for r in read_snapshots():
        if r.get("snapshot_id") == snapshot_id:
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
