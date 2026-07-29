"""Research Observability 원장 (P10.18) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 mh_ 접두사(Monitoring Health Intelligence). 각 레코드: id · timestamp · previous_hash ·
record_hash. 연구 시스템 건강 관찰·기록만 — 복구/실행/수정/재시작/배포 없음. 상위 레이어(P9.8~P10.17)는
**READ ONLY**. (주의: 접두사 ob_ 는 P10.10 research_observatory 소유이므로 재사용하지 않는다.)
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (mh_ 접두사)
HEALTH_RECORDS = ("mh_health_records.jsonl", "health_id")
METRICS = ("mh_metrics.jsonl", "metric_id")
SNAPSHOTS = ("mh_snapshots.jsonl", "snapshot_id")
ANOMALIES = ("mh_anomalies.jsonl", "event_id")            # 이벤트 소싱
ACTIVITY_EVENTS = ("mh_activity_events.jsonl", "activity_id")
QUALITY_HISTORY = ("mh_quality_history.jsonl", "quality_id")
REPORTS = ("mh_reports.jsonl", "report_id")
ARTIFACTS = ("mh_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (HEALTH_RECORDS, METRICS, SNAPSHOTS, ANOMALIES, ACTIVITY_EVENTS, QUALITY_HISTORY,
               REPORTS, ARTIFACTS)

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


# ── Health Records (불변) ──
def append_health(rec: dict) -> None:
    _append(HEALTH_RECORDS[0], rec)


def read_health() -> list[dict]:
    return read_jsonl(HEALTH_RECORDS[0])


def health_head() -> dict | None:
    return _head(HEALTH_RECORDS[0])


def health_exists(health_id: str) -> bool:
    return _exists(HEALTH_RECORDS[0], HEALTH_RECORDS[1], health_id)


def get_health(health_id: str) -> dict | None:
    for r in read_health():
        if r.get("health_id") == health_id:
            return r
    return None


# ── Metrics (불변) ──
def append_metric(rec: dict) -> None:
    _append(METRICS[0], rec)


def read_metrics() -> list[dict]:
    return read_jsonl(METRICS[0])


def metrics_head() -> dict | None:
    return _head(METRICS[0])


def metric_exists(metric_id: str) -> bool:
    return _exists(METRICS[0], METRICS[1], metric_id)


def get_metric(metric_id: str) -> dict | None:
    for r in read_metrics():
        if r.get("metric_id") == metric_id:
            return r
    return None


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


# ── Anomalies (event-sourced) ──
def append_anomaly_event(rec: dict) -> None:
    _append(ANOMALIES[0], rec)


def read_anomaly_events() -> list[dict]:
    return read_jsonl(ANOMALIES[0])


def anomalies_head() -> dict | None:
    return _head(ANOMALIES[0])


def anomaly_event_exists(event_id: str) -> bool:
    return _exists(ANOMALIES[0], ANOMALIES[1], event_id)


def anomaly_events_for(anomaly_id: str) -> list[dict]:
    return [r for r in read_anomaly_events() if r.get("anomaly_id") == anomaly_id]


def distinct_anomalies() -> list[dict]:
    out: dict = {}
    for r in read_anomaly_events():
        aid = r.get("anomaly_id")
        if aid not in out:
            out[aid] = r
    return list(out.values())


def anomaly_exists(anomaly_id: str) -> bool:
    return any(r.get("anomaly_id") == anomaly_id for r in read_anomaly_events())


# ── Activity Events ──
def append_activity(rec: dict) -> None:
    _append(ACTIVITY_EVENTS[0], rec)


def read_activity() -> list[dict]:
    return read_jsonl(ACTIVITY_EVENTS[0])


def activity_head() -> dict | None:
    return _head(ACTIVITY_EVENTS[0])


def activity_exists(activity_id: str) -> bool:
    return _exists(ACTIVITY_EVENTS[0], ACTIVITY_EVENTS[1], activity_id)


# ── Quality History ──
def append_quality(rec: dict) -> None:
    _append(QUALITY_HISTORY[0], rec)


def read_quality() -> list[dict]:
    return read_jsonl(QUALITY_HISTORY[0])


def quality_head() -> dict | None:
    return _head(QUALITY_HISTORY[0])


def quality_exists(quality_id: str) -> bool:
    return _exists(QUALITY_HISTORY[0], QUALITY_HISTORY[1], quality_id)


def quality_for(source_reference: str) -> list[dict]:
    return [r for r in read_quality() if r.get("source_reference") == source_reference]


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
