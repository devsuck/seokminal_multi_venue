"""Research Workflow 검증 — rwf_ 원장 해시체인 무결성(append-only). 읽기 전용."""
from __future__ import annotations

from jarvis.research_workflow import ledger
from jarvis.research_workflow.models import GENESIS, content_hash


def _verify_chain(rows) -> dict:
    prev = GENESIS
    for i, r in enumerate(rows):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broke_at": i, "reason": "previous_hash mismatch"}
        if r.get("record_hash") != content_hash(r):
            return {"ok": False, "broke_at": i, "reason": "record_hash mismatch"}
        prev = r["record_hash"]
    return {"ok": True, "n": len(rows)}


def verify_chain() -> dict:
    runs = _verify_chain(ledger.read_runs())
    sessions = _verify_chain(ledger.read_sessions())
    return {"ok": runs["ok"] and sessions["ok"], "runs": runs, "sessions": sessions}
