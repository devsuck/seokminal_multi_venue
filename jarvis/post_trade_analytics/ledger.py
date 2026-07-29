"""Post-Trade Analytics 원장 (P8.7) — append-only 해시체인. 삭제/재작성 없음. 진실=JSONL.

post_trade_reports.jsonl. 각 리포트: report_id·report_hash·previous_hash·timestamp.
분석 기록만 — 주문/집행/브로커/상태변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_REPORTS = "post_trade_reports.jsonl"


def append_report(report: dict) -> None:
    p = state_path(_REPORTS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")


def read_reports() -> list[dict]:
    p = state_path(_REPORTS)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def report_exists(report_id: str) -> bool:
    return any(r.get("report_id") == report_id for r in read_reports())


def chain_head() -> dict | None:
    reps = read_reports()
    return reps[-1] if reps else None


def last_report() -> dict | None:
    return chain_head()
