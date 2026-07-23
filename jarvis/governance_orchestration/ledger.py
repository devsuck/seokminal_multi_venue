"""Governance Orchestration 원장 (P10.23) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 go_ 접두사(Governance Orchestration). 각 레코드: id · timestamp · previous_hash · record_hash.
전 계층 관찰·집계 기록만 — 실행/거래/배포/config·permission 변경 없음. 상위 레이어(P9.8~P10.22)는 **READ ONLY**.
(주의: research_orchestration/or_ 는 P10.17 소유이므로 재사용하지 않는다.)
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (go_ 접두사)
LAYERS = ("go_layers.jsonl", "event_id")                  # 이벤트 소싱
STATUS = ("go_status.jsonl", "status_id")
DEPENDENCIES = ("go_dependencies.jsonl", "dependency_id")
SNAPSHOTS = ("go_snapshots.jsonl", "event_id")            # 이벤트 소싱
HEALTH = ("go_health.jsonl", "health_id")
CONFLICTS = ("go_conflicts.jsonl", "conflict_id")
REPORTS = ("go_reports.jsonl", "report_id")
ARTIFACTS = ("go_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (LAYERS, STATUS, DEPENDENCIES, SNAPSHOTS, HEALTH, CONFLICTS, REPORTS, ARTIFACTS)

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
    "governance_evolution": ("ge_events.jsonl", "event_id"),
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


def known_source_layers() -> list[str]:
    return sorted(SOURCE_LEDGERS.keys())


# ── Layers (event-sourced) ──
def append_layer_event(rec: dict) -> None:
    _append(LAYERS[0], rec)


def read_layer_events() -> list[dict]:
    return read_jsonl(LAYERS[0])


def layers_head() -> dict | None:
    return _head(LAYERS[0])


def layer_event_exists(event_id: str) -> bool:
    return _exists(LAYERS[0], LAYERS[1], event_id)


def layer_events_for(layer_id: str) -> list[dict]:
    return [r for r in read_layer_events() if r.get("layer_id") == layer_id]


def distinct_layers() -> list[dict]:
    out: dict = {}
    for r in read_layer_events():
        lid = r.get("layer_id")
        if lid not in out:
            out[lid] = r
    return list(out.values())


def layer_exists(layer_id: str) -> bool:
    return any(r.get("layer_id") == layer_id for r in read_layer_events())


# ── Status ──
def append_status(rec: dict) -> None:
    _append(STATUS[0], rec)


def read_status() -> list[dict]:
    return read_jsonl(STATUS[0])


def status_head() -> dict | None:
    return _head(STATUS[0])


def status_exists(status_id: str) -> bool:
    return _exists(STATUS[0], STATUS[1], status_id)


def get_status(status_id: str) -> dict | None:
    for r in read_status():
        if r.get("status_id") == status_id:
            return r
    return None


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


# ── Snapshots (event-sourced) ──
def append_snapshot_event(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshot_events() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_event_exists(event_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], event_id)


def snapshot_events_for(snapshot_id: str) -> list[dict]:
    return [r for r in read_snapshot_events() if r.get("snapshot_id") == snapshot_id]


def distinct_snapshots() -> list[dict]:
    out: dict = {}
    for r in read_snapshot_events():
        sid = r.get("snapshot_id")
        if sid not in out:
            out[sid] = r
    return list(out.values())


def snapshot_exists(snapshot_id: str) -> bool:
    return any(r.get("snapshot_id") == snapshot_id for r in read_snapshot_events())


# ── Health summaries ──
def append_health(rec: dict) -> None:
    _append(HEALTH[0], rec)


def read_health() -> list[dict]:
    return read_jsonl(HEALTH[0])


def health_head() -> dict | None:
    return _head(HEALTH[0])


def health_exists(health_id: str) -> bool:
    return _exists(HEALTH[0], HEALTH[1], health_id)


# ── Conflicts ──
def append_conflict(rec: dict) -> None:
    _append(CONFLICTS[0], rec)


def read_conflicts() -> list[dict]:
    return read_jsonl(CONFLICTS[0])


def conflicts_head() -> dict | None:
    return _head(CONFLICTS[0])


def conflict_exists(conflict_id: str) -> bool:
    return _exists(CONFLICTS[0], CONFLICTS[1], conflict_id)


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
