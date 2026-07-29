"""Reconciliation 원장 (P7.3) — append-only reconciliation_events.jsonl. 결정적 해시.

기록: report_hash, timestamp, severity, detected_issues. 삭제/재작성 없음.
"""
from __future__ import annotations

import hashlib
import json
import os

from jarvis.config import state_path
from jarvis.reconciliation.models import ReconciliationReport

_LEDGER = "reconciliation_events.jsonl"


def report_hash(report: ReconciliationReport) -> str:
    d = report.to_dict()
    blob = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def record_report(report: ReconciliationReport) -> dict:
    issues = [{"type": e["type"], "severity": e["severity"], "message": e["message"]}
              for e in report.control_events]
    row = {"report_hash": report_hash(report), "timestamp": report.timestamp,
           "severity": report.severity, "detected_issues": issues}
    p = state_path(_LEDGER)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def read_events() -> list[dict]:
    p = state_path(_LEDGER)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def last_event() -> dict | None:
    rows = read_events()
    return rows[-1] if rows else None
