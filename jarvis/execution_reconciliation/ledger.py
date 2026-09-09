"""Execution Reconciliation 원장 (P7.6) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

execution_validation_reports.jsonl · execution_reconciliation_events.jsonl.
검증 산출물만. 집행 게이트웨이 무관·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_REPORTS = "execution_validation_reports.jsonl"
_EVENTS = "execution_reconciliation_events.jsonl"


def append_report(report: dict) -> None:
    append(_REPORTS, report, resolver=state_path)


def append_event(event: dict) -> None:
    append(_EVENTS, event, resolver=state_path)


def read_reports() -> list[dict]:
    return read_jsonl(_REPORTS, resolver=state_path)


def read_events() -> list[dict]:
    return read_jsonl(_EVENTS, resolver=state_path)


def last_report() -> dict | None:
    rows = read_reports()
    return rows[-1] if rows else None


def validation_exists(validation_id: str) -> bool:
    return any(r.get("validation_id") == validation_id for r in read_reports())
