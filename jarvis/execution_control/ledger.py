"""Execution Control 원장 (P7.4) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

execution_intents.jsonl · execution_decisions.jsonl · execution_control_events.jsonl.
집행 게이트웨이 무관·주문 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_INTENTS = "execution_intents.jsonl"
_DECISIONS = "execution_decisions.jsonl"
_EVENTS = "execution_control_events.jsonl"


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


def append_intent(intent: dict) -> None:
    _append(_INTENTS, intent)


def append_decision(decision: dict) -> None:
    _append(_DECISIONS, decision)


def append_event(event: dict) -> None:
    _append(_EVENTS, event)


def read_intents() -> list[dict]:
    return _read(_INTENTS)


def read_decisions() -> list[dict]:
    return _read(_DECISIONS)


def read_events() -> list[dict]:
    return _read(_EVENTS)


def intent_exists(source_proposal_id: str) -> bool:
    return any(i.get("source_proposal_id") == source_proposal_id for i in read_intents())
