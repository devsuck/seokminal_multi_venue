"""Emergency 원장 (P9.3) — 4개 append-only 해시체인 + 관측 입력 데이터 리더. 진실=JSONL.

emergency_decisions.jsonl · recovery_requests.jsonl · recovery_approvals.jsonl ·
recovery_events.jsonl. 관측 입력(P9.1 헬스·P8.5 리스크·P9.2 인시던트/에스컬레이션)은
*데이터 파일로만* 읽는다 — 해당 계층 코드를 import 하지 않는다. 비상 결정 기록만.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드)
DECISIONS = ("emergency_decisions.jsonl", "decision_id")
RECOVERY_REQUESTS = ("recovery_requests.jsonl", "request_id")
RECOVERY_APPROVALS = ("recovery_approvals.jsonl", "approval_id")
RECOVERY_EVENTS = ("recovery_events.jsonl", "event_id")

ALL_LEDGERS = (DECISIONS, RECOVERY_REQUESTS, RECOVERY_APPROVALS, RECOVERY_EVENTS)

# 관측 입력(다른 계층이 소유) — 읽기전용 데이터 파일
_HEALTH_LEDGER = "system_health_reports.jsonl"      # P9.1
_RISK_LEDGER = "execution_risk_reports.jsonl"       # P8.5
_INCIDENTS_LEDGER = "incidents.jsonl"               # P9.2
_ESCALATIONS_LEDGER = "escalations.jsonl"           # P9.2


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read(filename: str) -> list[dict]:
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
    recs = _read(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in _read(filename))


# ── Emergency Decisions ──
def append_decision(rec: dict) -> None:
    _append(DECISIONS[0], rec)


def read_decisions() -> list[dict]:
    return _read(DECISIONS[0])


def decision_exists(decision_id: str) -> bool:
    return _exists(DECISIONS[0], DECISIONS[1], decision_id)


def decisions_head() -> dict | None:
    return _head(DECISIONS[0])


# ── Recovery Requests ──
def append_recovery_request(rec: dict) -> None:
    _append(RECOVERY_REQUESTS[0], rec)


def read_recovery_requests() -> list[dict]:
    return _read(RECOVERY_REQUESTS[0])


def recovery_request_exists(request_id: str) -> bool:
    return _exists(RECOVERY_REQUESTS[0], RECOVERY_REQUESTS[1], request_id)


def recovery_requests_head() -> dict | None:
    return _head(RECOVERY_REQUESTS[0])


# ── Recovery Approvals ──
def append_recovery_approval(rec: dict) -> None:
    _append(RECOVERY_APPROVALS[0], rec)


def read_recovery_approvals() -> list[dict]:
    return _read(RECOVERY_APPROVALS[0])


def recovery_approval_exists(approval_id: str) -> bool:
    return _exists(RECOVERY_APPROVALS[0], RECOVERY_APPROVALS[1], approval_id)


def recovery_approvals_head() -> dict | None:
    return _head(RECOVERY_APPROVALS[0])


# ── Recovery Events ──
def append_recovery_event(rec: dict) -> None:
    _append(RECOVERY_EVENTS[0], rec)


def read_recovery_events() -> list[dict]:
    return _read(RECOVERY_EVENTS[0])


def recovery_event_exists(event_id: str) -> bool:
    return _exists(RECOVERY_EVENTS[0], RECOVERY_EVENTS[1], event_id)


def recovery_events_head() -> dict | None:
    return _head(RECOVERY_EVENTS[0])


# ── 관측 입력 리더(데이터 파일로만) ──
def latest_health() -> dict:
    recs = _read(_HEALTH_LEDGER)
    return recs[-1] if recs else {}


def latest_risk() -> dict:
    recs = _read(_RISK_LEDGER)
    return recs[-1] if recs else {}


def read_incident_rows() -> list[dict]:
    return _read(_INCIDENTS_LEDGER)


def read_escalation_rows() -> list[dict]:
    return _read(_ESCALATIONS_LEDGER)
