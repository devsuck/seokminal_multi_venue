"""Broker Read-Only 감사 (P7.1) — append-only broker_readonly_events.jsonl.

기록: provider, query, timestamp, result_hash. 삭제/재작성 없음. 결정적 해시.
"""
from __future__ import annotations

import hashlib
import json
import os

from jarvis.config import state_path

_LEDGER = "broker_readonly_events.jsonl"


def result_hash(result) -> str:
    blob = json.dumps(result, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def record_query(provider: str, query: str, timestamp: str, result) -> dict:
    """읽기 쿼리 감사 append. 반환: 기록 행."""
    row = {"provider": provider, "query": query, "timestamp": timestamp,
           "result_hash": result_hash(result)}
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
