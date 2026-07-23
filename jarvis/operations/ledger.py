"""Operations 원장 (P9.2) — 5개 append-only 해시체인. 삭제/재작성 없음. 진실=JSONL.

alerts.jsonl · incidents.jsonl · escalations.jsonl · acknowledgements.jsonl · resolution.jsonl
각 레코드: id·record_hash·previous_hash·timestamp. 관제 기록만 —
주문/집행/브로커/킬스위치/상태변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — verify 가 id 필드로 중복을 탐지
ALERTS = ("alerts.jsonl", "alert_id")
INCIDENTS = ("incidents.jsonl", "event_id")              # 이벤트 소싱(전이 이벤트별 고유 id)
ESCALATIONS = ("escalations.jsonl", "escalation_id")
ACKS = ("acknowledgements.jsonl", "ack_id")
RESOLUTIONS = ("resolution.jsonl", "resolution_id")

ALL_LEDGERS = (ALERTS, INCIDENTS, ESCALATIONS, ACKS, RESOLUTIONS)


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read(filename: str) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _head(filename: str) -> dict | None:
    recs = _read(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in _read(filename))


# ── Alerts ──
def append_alert(rec: dict) -> None:
    _append(ALERTS[0], rec)


def read_alerts() -> list[dict]:
    return _read(ALERTS[0])


def alert_exists(alert_id: str) -> bool:
    return _exists(ALERTS[0], ALERTS[1], alert_id)


def alerts_head() -> dict | None:
    return _head(ALERTS[0])


def count_alerts_by_key(a_key: str) -> int:
    return sum(1 for r in read_alerts() if r.get("alert_key") == a_key)


# ── Incidents (event-sourced) ──
def append_incident(rec: dict) -> None:
    _append(INCIDENTS[0], rec)


def read_incidents() -> list[dict]:
    return _read(INCIDENTS[0])


def incident_event_exists(incident_id: str, from_state: str, to_state: str) -> bool:
    """동일 전이 이벤트 중복 방지(같은 incident 의 동일 from→to)."""
    for r in read_incidents():
        if (r.get("incident_id") == incident_id and r.get("from_state") == from_state
                and r.get("to_state") == to_state):
            return True
    return False


def incidents_head() -> dict | None:
    return _head(INCIDENTS[0])


def incident_events(incident_id: str) -> list[dict]:
    return [r for r in read_incidents() if r.get("incident_id") == incident_id]


def active_incident_for_key(a_key: str, active_states: set) -> str | None:
    """해당 alert_key 의 활성 인시던트 id(없으면 None). dedup 용."""
    latest: dict = {}
    for r in read_incidents():
        if r.get("alert_key") == a_key:
            latest[r["incident_id"]] = r.get("to_state", "")
    for inc_id, state in latest.items():
        if state in active_states:
            return inc_id
    return None


# ── Escalations ──
def append_escalation(rec: dict) -> None:
    _append(ESCALATIONS[0], rec)


def read_escalations() -> list[dict]:
    return _read(ESCALATIONS[0])


def escalation_exists(escalation_id: str) -> bool:
    return _exists(ESCALATIONS[0], ESCALATIONS[1], escalation_id)


def escalations_head() -> dict | None:
    return _head(ESCALATIONS[0])


def escalation_count(incident_id: str) -> int:
    return sum(1 for r in read_escalations() if r.get("incident_id") == incident_id)


# ── Acknowledgements ──
def append_ack(rec: dict) -> None:
    _append(ACKS[0], rec)


def read_acks() -> list[dict]:
    return _read(ACKS[0])


def ack_exists(ack_id: str) -> bool:
    return _exists(ACKS[0], ACKS[1], ack_id)


def acks_head() -> dict | None:
    return _head(ACKS[0])


# ── Resolutions ──
def append_resolution(rec: dict) -> None:
    _append(RESOLUTIONS[0], rec)


def read_resolutions() -> list[dict]:
    return _read(RESOLUTIONS[0])


def resolution_exists(resolution_id: str) -> bool:
    return _exists(RESOLUTIONS[0], RESOLUTIONS[1], resolution_id)


def resolutions_head() -> dict | None:
    return _head(RESOLUTIONS[0])
