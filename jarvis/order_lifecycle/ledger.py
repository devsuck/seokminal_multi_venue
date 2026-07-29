"""Order Lifecycle 원장 (P8.2) — append-only 해시체인. 삭제/재작성 없음. 소스 진실=JSONL.

order_lifecycle_events.jsonl. 각 이벤트: event_hash · previous_hash · timestamp.
관측 기록만 — 브로커 호출 없음·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_EVENTS = "order_lifecycle_events.jsonl"


def _read(name: str) -> list[dict]:
    p = state_path(name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append_event(event: dict) -> None:
    p = state_path(_EVENTS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def read_events() -> list[dict]:
    return _read(_EVENTS)


def events_for(order_id: str) -> list[dict]:
    return [e for e in read_events() if e.get("order_id") == order_id]


def event_exists(event_id: str) -> bool:
    return any(e.get("event_id") == event_id for e in read_events())


def chain_head(order_id: str) -> dict | None:
    """해당 주문의 최신(체인 말단) 이벤트."""
    evs = events_for(order_id)
    return evs[-1] if evs else None
