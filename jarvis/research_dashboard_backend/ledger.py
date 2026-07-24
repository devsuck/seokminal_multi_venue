"""Research Dashboard Backend 원장 (P34) — 5개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rdb_ 접두사(Research DashBoard). 각 레코드: id · timestamp · previous_hash · record_hash. 백엔드 집계
기록만 — UI·결정·실행 없음. 상위 계층(P10~P33)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

PANELS = ("rdb_panels.jsonl", "panel_id")                       # 패널 정의
SNAPSHOTS = ("rdb_snapshots.jsonl", "snapshot_id")            # 집계 스냅샷
WIDGETS = ("rdb_widgets.jsonl", "widget_id")                  # 위젯/지표
REPORTS = ("rdb_reports.jsonl", "report_id")                 # 대시보드 리포트
ARTIFACTS = ("rdb_artifacts.jsonl", "artifact_id")          # 계보

ALL_LEDGERS = (PANELS, SNAPSHOTS, WIDGETS, REPORTS, ARTIFACTS)

# ── 대시보드 집계 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),               # P10.5
    "memory_intelligence": ("rmi_memories.jsonl", "memory_event_id"),    # P27
    "insight_intelligence": ("rii_insights.jsonl", "insight_event_id"),  # P28
    "meta_intelligence": ("mri_meta_metrics.jsonl", "metric_id"),        # P30
    "monitoring_health": ("rmon_health_checks.jsonl", "health_id"),      # P23
    "monitoring_anomalies": ("rmon_anomalies.jsonl", "anomaly_id"),      # P23
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),        # P24
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),       # P25
    "strategy_generation": ("rsg_candidates.jsonl", "candidate_event_id"),  # P29
    "orchestration": ("exo_plans.jsonl", "plan_event_id"),             # P31
    "resource_manager": ("rrm_resources.jsonl", "resource_id"),        # P32
    "agent_coordination": ("racd_sessions.jsonl", "session_event_id"),  # P26
}


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
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


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename, id_field, rid) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_present(layer) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def source_records(layer) -> list[dict]:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return []
    return read_jsonl(spec[0])


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec)

    def read():
        return read_jsonl(fname)

    def head():
        return _head(fname)

    def exists(rid):
        return _exists(fname, idf, rid)

    return append, read, head, exists


append_panel, read_panels, panels_head, panel_exists = _readers(PANELS)
append_snapshot, read_snapshots, snapshots_head, snapshot_exists = _readers(SNAPSHOTS)
append_widget, read_widgets, widgets_head, widget_exists = _readers(WIDGETS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def widgets_by_panel(panel_type) -> list[dict]:
    return [r for r in read_widgets() if r.get("panel_type") == panel_type]
