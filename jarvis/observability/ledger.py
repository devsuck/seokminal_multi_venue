"""Observability 원장 (P17) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 obs_ 접두사(OBServability). 각 레코드: id · timestamp · previous_hash · record_hash · metadata. 모니터·
측정·기록만 — 실행·자동조치 없음. 상위 계층(P9~P16)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (obs_ 접두사)
PIPELINE_HEALTH = ("obs_pipeline_health.jsonl", "health_event_id")     # 건강 생애주기(event-sourced)
SYSTEM_METRICS = ("obs_system_metrics.jsonl", "metric_id")            # 시스템 지표
HEALTH_EVENTS = ("obs_health_events.jsonl", "observation_id")         # 관찰(데이터 품질/무결성)
ALERT_EVENTS = ("obs_alert_events.jsonl", "alert_id")                 # 알림(기록 전용)
PERFORMANCE_SNAPSHOTS = ("obs_performance_snapshots.jsonl", "perf_id")  # 성능 스냅샷
AVAILABILITY_RECORDS = ("obs_availability_records.jsonl", "availability_id")  # 가용성
AUDIT_OBSERVATIONS = ("obs_audit_observations.jsonl", "audit_obs_id")  # 감사 가시성
ARTIFACTS = ("obs_observability_artifacts.jsonl", "artifact_id")      # 아티팩트 계보

ALL_LEDGERS = (PIPELINE_HEALTH, SYSTEM_METRICS, HEALTH_EVENTS, ALERT_EVENTS,
               PERFORMANCE_SNAPSHOTS, AVAILABILITY_RECORDS, AUDIT_OBSERVATIONS, ARTIFACTS)

# ── 모니터 대상(READ ONLY 소스) — 로직명 → (라벨, 파일, id 필드). import 결합 없음. ──
MONITOR_TARGETS = {
    "strategy_governance": ("P10.2 Strategy Governance", "mg_models.jsonl", "model_hash"),
    "alpha_intelligence": ("P10.3 Alpha Intelligence", "ai_signals.jsonl", "signal_hash"),
    "portfolio_research": ("P10.4 Portfolio Research", "pr_portfolios.jsonl", "portfolio_hash"),
    "knowledge_graph": ("P10.5 Knowledge Graph", "kg_entities.jsonl", "event_id"),
    "agent_governance": ("P10.6 Agent Governance", "arg_agents.jsonl", "event_id"),
    "decision_intelligence": ("P10.7 Decision Intelligence", "di_candidates.jsonl", "event_id"),
    "simulation": ("P10.8 Simulation", "sim_scenarios.jsonl", "event_id"),
    "security": ("P15 Security", "", ""),  # stateless — 소스 원장 없음(가시성만)
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


# ── 모니터 대상 READ ONLY ──
def source_count(target: str) -> int:
    """모니터 대상 원장의 레코드 수(READ ONLY). stateless 대상은 0."""
    spec = MONITOR_TARGETS.get(target)
    if not spec or not spec[1]:
        return 0
    return len(read_jsonl(spec[1]))


def all_target_counts() -> dict:
    """모든 모니터 대상의 레코드 수(결정적, READ ONLY)."""
    return {t: source_count(t) for t in sorted(MONITOR_TARGETS)}


# ── Pipeline Health (event-sourced) ──
def append_health_event(rec: dict) -> None:
    _append(PIPELINE_HEALTH[0], rec)


def read_health_events() -> list[dict]:
    return read_jsonl(PIPELINE_HEALTH[0])


def health_head() -> dict | None:
    return _head(PIPELINE_HEALTH[0])


def health_event_exists(hid: str) -> bool:
    return _exists(PIPELINE_HEALTH[0], PIPELINE_HEALTH[1], hid)


def target_events(target_id: str) -> list[dict]:
    return [r for r in read_health_events() if r.get("target_id") == target_id]


def target_ids() -> list[str]:
    return sorted({r.get("target_id") for r in read_health_events() if r.get("target_id")})


# ── System Metrics ──
def append_metric(rec: dict) -> None:
    _append(SYSTEM_METRICS[0], rec)


def read_metrics() -> list[dict]:
    return read_jsonl(SYSTEM_METRICS[0])


def metrics_head() -> dict | None:
    return _head(SYSTEM_METRICS[0])


def metric_exists(mid: str) -> bool:
    return _exists(SYSTEM_METRICS[0], SYSTEM_METRICS[1], mid)


def metrics_by_key(key: str) -> list[dict]:
    return [r for r in read_metrics() if r.get("key") == key]


# ── Observations (data quality / integrity) ──
def append_observation(rec: dict) -> None:
    _append(HEALTH_EVENTS[0], rec)


def read_observations() -> list[dict]:
    return read_jsonl(HEALTH_EVENTS[0])


def observations_head() -> dict | None:
    return _head(HEALTH_EVENTS[0])


def observation_exists(oid: str) -> bool:
    return _exists(HEALTH_EVENTS[0], HEALTH_EVENTS[1], oid)


# ── Alerts ──
def append_alert(rec: dict) -> None:
    _append(ALERT_EVENTS[0], rec)


def read_alerts() -> list[dict]:
    return read_jsonl(ALERT_EVENTS[0])


def alerts_head() -> dict | None:
    return _head(ALERT_EVENTS[0])


def alert_exists(aid: str) -> bool:
    return _exists(ALERT_EVENTS[0], ALERT_EVENTS[1], aid)


# ── Performance ──
def append_perf(rec: dict) -> None:
    _append(PERFORMANCE_SNAPSHOTS[0], rec)


def read_perf() -> list[dict]:
    return read_jsonl(PERFORMANCE_SNAPSHOTS[0])


def perf_head() -> dict | None:
    return _head(PERFORMANCE_SNAPSHOTS[0])


def perf_exists(pid: str) -> bool:
    return _exists(PERFORMANCE_SNAPSHOTS[0], PERFORMANCE_SNAPSHOTS[1], pid)


# ── Availability ──
def append_availability(rec: dict) -> None:
    _append(AVAILABILITY_RECORDS[0], rec)


def read_availability() -> list[dict]:
    return read_jsonl(AVAILABILITY_RECORDS[0])


def availability_head() -> dict | None:
    return _head(AVAILABILITY_RECORDS[0])


def availability_exists(aid: str) -> bool:
    return _exists(AVAILABILITY_RECORDS[0], AVAILABILITY_RECORDS[1], aid)


# ── Audit Observations ──
def append_audit(rec: dict) -> None:
    _append(AUDIT_OBSERVATIONS[0], rec)


def read_audit() -> list[dict]:
    return read_jsonl(AUDIT_OBSERVATIONS[0])


def audit_head() -> dict | None:
    return _head(AUDIT_OBSERVATIONS[0])


def audit_exists(aid: str) -> bool:
    return _exists(AUDIT_OBSERVATIONS[0], AUDIT_OBSERVATIONS[1], aid)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(aid: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], aid)
