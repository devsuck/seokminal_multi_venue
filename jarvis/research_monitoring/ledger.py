"""Research Monitoring 원장 (P23) — 9개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rmon_ 접두사(Research MONitoring). 각 레코드: id · timestamp · previous_hash · record_hash. 관찰·기록만
— 실행·제어 없음. 상위 계층(P9.8~P22)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

SESSIONS = ("rmon_sessions.jsonl", "session_event_id")           # 모니터링 세션 생애주기(ES)
METRICS = ("rmon_metrics.jsonl", "metric_id")                    # 건강/활동 지표
HEALTH_CHECKS = ("rmon_health_checks.jsonl", "health_id")        # 헬스 체크
OBSERVATIONS = ("rmon_observations.jsonl", "observation_id")     # 관찰
ACTIVITY_EVENTS = ("rmon_activity_events.jsonl", "activity_event_id")  # 활동 이벤트
ANOMALIES = ("rmon_anomalies.jsonl", "anomaly_id")               # 시스템 이상
SNAPSHOTS = ("rmon_snapshots.jsonl", "snapshot_id")             # 모니터링 스냅샷
REPORTS = ("rmon_reports.jsonl", "report_id")                   # 관측성 리포트
ARTIFACTS = ("rmon_artifacts.jsonl", "artifact_id")            # 아티팩트 계보

ALL_LEDGERS = (SESSIONS, METRICS, HEALTH_CHECKS, OBSERVATIONS, ACTIVITY_EVENTS, ANOMALIES,
               SNAPSHOTS, REPORTS, ARTIFACTS)

# ── 모니터 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_hash"),           # P9.8
    "simulation": ("sim_scenarios.jsonl", "event_id"),                # P10.8
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),     # P10.7
    "research_operations": ("ro_workflows.jsonl", "workflow_event_id"),  # P18
    "continuous_learning": ("cl_memories.jsonl", "memory_event_id"),  # P20
    "production_readiness": ("pd_candidates.jsonl", "candidate_id"),  # P21
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),  # P22
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


# ── 모니터 대상 READ ONLY ──
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


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


# ── helper 팩토리 ──
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


append_session_event, read_session_events, sessions_head, session_event_exists = _readers(SESSIONS)
append_metric, read_metrics, metrics_head, metric_exists = _readers(METRICS)
append_health, read_health_checks, health_head, health_exists = _readers(HEALTH_CHECKS)
append_observation, read_observations, observations_head, observation_exists = _readers(OBSERVATIONS)
append_activity, read_activity_events, activity_head, activity_exists = _readers(ACTIVITY_EVENTS)
append_anomaly, read_anomalies, anomalies_head, anomaly_exists = _readers(ANOMALIES)
append_snapshot, read_snapshots, snapshots_head, snapshot_exists = _readers(SNAPSHOTS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def session_events(sess) -> list[dict]:
    return [r for r in read_session_events() if r.get("session_id") == sess]


def session_ids() -> list[str]:
    return sorted({r.get("session_id") for r in read_session_events() if r.get("session_id")})


def metrics_by_name(name) -> list[dict]:
    return [r for r in read_metrics() if r.get("metric_name") == name]


def component_health(component) -> list[dict]:
    return [r for r in read_health_checks() if r.get("component") == component]
