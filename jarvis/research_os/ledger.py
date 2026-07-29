"""Research OS Orchestration 원장 (P11) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ros_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 오케스트레이션 관찰
기록만 — 실행/거래/배포/config 변경 없음. 상위 레이어(P9.8~P10.15)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ros_ 접두사)
LAYERS = ("ros_layers.jsonl", "event_id")               # 이벤트 소싱
WORKFLOWS = ("ros_workflows.jsonl", "event_id")         # 이벤트 소싱
EVENTS = ("ros_events.jsonl", "event_id")
SNAPSHOTS = ("ros_snapshots.jsonl", "event_id")         # 이벤트 소싱
DEPENDENCIES = ("ros_dependencies.jsonl", "dependency_id")
HEALTH_REPORTS = ("ros_health_reports.jsonl", "health_report_id")
LINEAGE = ("ros_lineage.jsonl", "lineage_id")
ARTIFACTS = ("ros_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (LAYERS, WORKFLOWS, EVENTS, SNAPSHOTS, DEPENDENCIES, HEALTH_REPORTS, LINEAGE,
               ARTIFACTS)

# 전 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
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
    "data_governance_lineage": ("dg_lineage_events.jsonl", "lineage_id"),
    "research_validation": ("rv_validations.jsonl", "event_id"),
    "research_observatory": ("ob_snapshots.jsonl", "event_id"),
    "causal_intelligence": ("ci_hypotheses.jsonl", "event_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_opportunities.jsonl", "event_id"),
    "research_memory": ("rm_memories.jsonl", "event_id"),
    "research_planning": ("rp_opportunities.jsonl", "event_id"),
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


# ── Cross layer events ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(event_id: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], event_id)


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


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


# ── Health reports ──
def append_health_report(rec: dict) -> None:
    _append(HEALTH_REPORTS[0], rec)


def read_health_reports() -> list[dict]:
    return read_jsonl(HEALTH_REPORTS[0])


def health_head() -> dict | None:
    return _head(HEALTH_REPORTS[0])


def health_report_exists(health_report_id: str) -> bool:
    return _exists(HEALTH_REPORTS[0], HEALTH_REPORTS[1], health_report_id)


# ── Lineage ──
def append_lineage(rec: dict) -> None:
    _append(LINEAGE[0], rec)


def read_lineage() -> list[dict]:
    return read_jsonl(LINEAGE[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE[0])


def lineage_exists(lineage_id: str) -> bool:
    return _exists(LINEAGE[0], LINEAGE[1], lineage_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
