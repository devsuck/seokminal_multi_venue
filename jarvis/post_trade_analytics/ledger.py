"""Post-Trade Analytics 원장 (P8.7) — append-only 해시체인. 삭제/재작성 없음. 진실=JSONL.

post_trade_reports.jsonl. 각 리포트: report_id·report_hash·previous_hash·timestamp.
분석 기록만 — 주문/집행/브로커/상태변경 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_REPORTS = "post_trade_reports.jsonl"


def append_report(report: dict) -> None:
    append(_REPORTS, report, resolver=state_path)


def read_reports() -> list[dict]:
    return read_jsonl(_REPORTS, resolver=state_path)


def report_exists(report_id: str) -> bool:
    return any(r.get("report_id") == report_id for r in read_reports())


def chain_head() -> dict | None:
    reps = read_reports()
    return reps[-1] if reps else None


def last_report() -> dict | None:
    return chain_head()
