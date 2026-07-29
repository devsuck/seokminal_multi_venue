"""Autonomous Research Control Plane 원장 (P12.10) — 7개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rctl_ 접두사(Research ConTroL). 각 레코드: id · timestamp · previous_hash · record_hash. 관찰·분석·기록만
— 자동 복구·배포·결정 없음. 상위 계층(P10.x/P12.x)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (rctl_ 접두사)
STATES = ("rctl_states.jsonl", "state_event_id")     # Research State Registry(event-sourced)
EVENTS = ("rctl_events.jsonl", "event_id")           # Research Events
HEALTH = ("rctl_health.jsonl", "health_id")          # Health Monitoring
METRICS = ("rctl_metrics.jsonl", "metric_id")        # Metrics
ALERTS = ("rctl_alerts.jsonl", "alert_id")           # Anomaly Alerts(record-only)
REPORTS = ("rctl_reports.jsonl", "report_id")        # System Reports
ARTIFACTS = ("rctl_artifacts.jsonl", "artifact_id")  # Artifact Lineage

ALL_LEDGERS = (STATES, EVENTS, HEALTH, METRICS, ALERTS, REPORTS, ARTIFACTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),         # P10.7
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),         # P12.1
    "research_experience_memory": ("rxm_memories.jsonl", "memory_event_id"),  # P12.7
    "research_learning": ("rll_loops.jsonl", "loop_event_id"),                # P12.8
    "research_manager": ("rmgr_plans.jsonl", "plan_event_id"),                # P12.9
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


def _get(filename: str, id_field: str, rid: str) -> dict | None:
    for r in read_jsonl(filename):
        if r.get(id_field) == rid:
            return r
    return None


# ── 상위 소스 READ ONLY ──
def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── States (event-sourced) ──
def append_state_event(rec: dict) -> None:
    _append(STATES[0], rec)


def read_state_events() -> list[dict]:
    return read_jsonl(STATES[0])


def states_head() -> dict | None:
    return _head(STATES[0])


def state_event_exists(sid: str) -> bool:
    return _exists(STATES[0], STATES[1], sid)


def state_events(state_id: str) -> list[dict]:
    return [r for r in read_state_events() if r.get("state_id") == state_id]


def state_ids() -> list[str]:
    return sorted({r.get("state_id") for r in read_state_events() if r.get("state_id")})


# ── Events ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_exists(eid: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], eid)


def state_records(state_id: str) -> list[dict]:
    return [r for r in read_events() if r.get("state_id") == state_id]


# ── Health ──
def append_health(rec: dict) -> None:
    _append(HEALTH[0], rec)


def read_health() -> list[dict]:
    return read_jsonl(HEALTH[0])


def health_head() -> dict | None:
    return _head(HEALTH[0])


def health_exists(hid: str) -> bool:
    return _exists(HEALTH[0], HEALTH[1], hid)


def state_health(state_id: str) -> list[dict]:
    return [r for r in read_health() if r.get("state_id") == state_id]


# ── Metrics ──
def append_metric(rec: dict) -> None:
    _append(METRICS[0], rec)


def read_metrics() -> list[dict]:
    return read_jsonl(METRICS[0])


def metrics_head() -> dict | None:
    return _head(METRICS[0])


def metric_exists(mid: str) -> bool:
    return _exists(METRICS[0], METRICS[1], mid)


def state_metrics(state_id: str) -> list[dict]:
    return [r for r in read_metrics() if r.get("state_id") == state_id]


# ── Alerts ──
def append_alert(rec: dict) -> None:
    _append(ALERTS[0], rec)


def read_alerts() -> list[dict]:
    return read_jsonl(ALERTS[0])


def alerts_head() -> dict | None:
    return _head(ALERTS[0])


def alert_exists(aid: str) -> bool:
    return _exists(ALERTS[0], ALERTS[1], aid)


def state_alerts(state_id: str) -> list[dict]:
    return [r for r in read_alerts() if r.get("state_id") == state_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(rid: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], rid)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(aid: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], aid)
