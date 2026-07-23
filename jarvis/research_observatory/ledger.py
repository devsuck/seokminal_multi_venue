"""Research Observatory 원장 (P10.10) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ob_ 접두사. 각 레코드: id · previous_hash · record_hash · timestamp. 관측·집계 기록만 —
실행/거래/배포 없음. 상위 레이어(P10.2~P10.9) 원장은 **READ ONLY** 로만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ob_ 접두사)
SNAPSHOTS = ("ob_snapshots.jsonl", "event_id")          # 이벤트 소싱
METRICS = ("ob_metrics.jsonl", "metric_id")
TIMELINES = ("ob_timelines.jsonl", "timeline_id")
DEPENDENCIES = ("ob_dependencies.jsonl", "dependency_id")
TRENDS = ("ob_trends.jsonl", "trend_id")
REPORTS = ("ob_reports.jsonl", "report_id")
DASHBOARDS = ("ob_dashboards.jsonl", "dashboard_id")
ARTIFACTS = ("ob_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (SNAPSHOTS, METRICS, TIMELINES, DEPENDENCIES, TRENDS, REPORTS, DASHBOARDS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
# layer -> (filename, id_field, created_at_field, event_sourced)
SOURCE_LEDGERS = {
    "STRATEGY": ("rg_strategies.jsonl", "strategy_id", "created_at", False),
    "SIGNAL": ("ai_signals.jsonl", "signal_id", "created_at", False),
    "FEATURE": ("ai_features.jsonl", "feature_id", "created_at", False),
    "DATASET": ("dg_datasets.jsonl", "dataset_id", "created_at", False),
    "EXPERIMENT": ("rg_experiments.jsonl", "experiment_id", "created_at", False),
    "PORTFOLIO": ("pr_portfolios.jsonl", "portfolio_id", "created_at", False),
    "VALIDATION": ("rv_validations.jsonl", "validation_id", "created_at", True),
    "DECISION": ("di_decision_sessions.jsonl", "session_id", "created_at", True),
    "SIMULATION": ("sim_runs.jsonl", "run_id", "created_at", True),
    "KG_ENTITY": ("kg_entities.jsonl", "entity_id", "created_at", True),
    "KG_RELATION": ("kg_relationships.jsonl", "relationship_id", "created_at", False),
    "REPLAY": ("rv_replay_reports.jsonl", "replay_id", "created_at", False),
    "AGENT": ("arg_agents.jsonl", "agent_id", "created_at", True),
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


def count_source(layer: str) -> int:
    """레이어의 개체 수(이벤트 소싱이면 distinct id). READ ONLY."""
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return 0
    filename, id_field, _created, event_sourced = spec
    rows = read_source(filename)
    if event_sourced:
        return len({r.get(id_field) for r in rows if r.get(id_field) is not None})
    return len(rows)


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


# ── Metrics ──
def append_metric(rec: dict) -> None:
    _append(METRICS[0], rec)


def read_metrics() -> list[dict]:
    return read_jsonl(METRICS[0])


def metrics_head() -> dict | None:
    return _head(METRICS[0])


def metric_exists(metric_id: str) -> bool:
    return _exists(METRICS[0], METRICS[1], metric_id)


def metrics_for_snapshot(snapshot_id: str) -> list[dict]:
    return [r for r in read_metrics() if r.get("snapshot_id") == snapshot_id]


def metric_value(snapshot_id: str, layer: str, metric_name: str) -> float | None:
    for r in read_metrics():
        if (r.get("snapshot_id") == snapshot_id and r.get("layer") == layer
                and r.get("metric_name") == metric_name):
            return r.get("value")
    return None


# ── Timelines ──
def append_timeline(rec: dict) -> None:
    _append(TIMELINES[0], rec)


def read_timelines() -> list[dict]:
    return read_jsonl(TIMELINES[0])


def timelines_head() -> dict | None:
    return _head(TIMELINES[0])


def timeline_exists(timeline_id: str) -> bool:
    return _exists(TIMELINES[0], TIMELINES[1], timeline_id)


def timelines_for_snapshot(snapshot_id: str) -> list[dict]:
    return [r for r in read_timelines() if r.get("snapshot_id") == snapshot_id]


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


def dependencies_for_snapshot(snapshot_id: str) -> list[dict]:
    return [r for r in read_dependencies() if r.get("snapshot_id") == snapshot_id]


# ── Trends ──
def append_trend(rec: dict) -> None:
    _append(TRENDS[0], rec)


def read_trends() -> list[dict]:
    return read_jsonl(TRENDS[0])


def trends_head() -> dict | None:
    return _head(TRENDS[0])


def trend_exists(trend_id: str) -> bool:
    return _exists(TRENDS[0], TRENDS[1], trend_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Dashboards ──
def append_dashboard(rec: dict) -> None:
    _append(DASHBOARDS[0], rec)


def read_dashboards() -> list[dict]:
    return read_jsonl(DASHBOARDS[0])


def dashboards_head() -> dict | None:
    return _head(DASHBOARDS[0])


def dashboard_exists(dashboard_id: str) -> bool:
    return _exists(DASHBOARDS[0], DASHBOARDS[1], dashboard_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
