"""Fill Reconciliation 원장 (P8.3) — append-only 해시체인. 삭제/재작성 없음. 진실=JSONL.

fill_reconciliation_events.jsonl. 각 이벤트: event_id·order_id·broker_order_id·status·
input_hash·report_hash·previous_hash·timestamp. 관측/대조 기록만.
브로커 write 없음·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_EVENTS = "fill_reconciliation_events.jsonl"


def append_event(event: dict) -> None:
    p = state_path(_EVENTS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def read_events() -> list[dict]:
    p = state_path(_EVENTS)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def event_exists(event_id: str) -> bool:
    return any(e.get("event_id") == event_id for e in read_events())


def chain_head() -> dict | None:
    evs = read_events()
    return evs[-1] if evs else None


def last_event() -> dict | None:
    return chain_head()
