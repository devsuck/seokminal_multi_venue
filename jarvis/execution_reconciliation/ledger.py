"""Execution Reconciliation 원장 (P7.6) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

execution_validation_reports.jsonl · execution_reconciliation_events.jsonl.
검증 산출물만. 집행 게이트웨이 무관·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_REPORTS = "execution_validation_reports.jsonl"
_EVENTS = "execution_reconciliation_events.jsonl"


def _read(name: str) -> list[dict]:
    p = state_path(name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(name: str, row: dict) -> None:
    p = state_path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def append_report(report: dict) -> None:
    _append(_REPORTS, report)


def append_event(event: dict) -> None:
    _append(_EVENTS, event)


def read_reports() -> list[dict]:
    return _read(_REPORTS)


def read_events() -> list[dict]:
    return _read(_EVENTS)


def last_report() -> dict | None:
    rows = read_reports()
    return rows[-1] if rows else None


def validation_exists(validation_id: str) -> bool:
    return any(r.get("validation_id") == validation_id for r in read_reports())
