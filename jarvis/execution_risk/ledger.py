"""Execution Risk 원장 (P8.5) — append-only 해시체인. 삭제/재작성 없음. 진실=JSONL.

execution_risk_reports.jsonl. 각 이벤트: event_id·request_id·overall_status·input_hash·
report_hash·previous_hash·timestamp. 평가 기록만 — 주문/집행/브로커/상태변경 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_EVENTS = "execution_risk_reports.jsonl"


def append_event(event: dict) -> None:
    append(_EVENTS, event, resolver=state_path)


def read_events() -> list[dict]:
    return read_jsonl(_EVENTS, resolver=state_path)


def event_exists(event_id: str) -> bool:
    return any(e.get("event_id") == event_id for e in read_events())


def chain_head() -> dict | None:
    evs = read_events()
    return evs[-1] if evs else None


def last_event() -> dict | None:
    return chain_head()
