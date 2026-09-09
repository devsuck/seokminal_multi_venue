"""Execution Control 원장 (P7.4) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

execution_intents.jsonl · execution_decisions.jsonl · execution_control_events.jsonl.
집행 게이트웨이 무관·주문 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_INTENTS = "execution_intents.jsonl"
_DECISIONS = "execution_decisions.jsonl"
_EVENTS = "execution_control_events.jsonl"


def append_intent(intent: dict) -> None:
    append(_INTENTS, intent, resolver=state_path)


def append_decision(decision: dict) -> None:
    append(_DECISIONS, decision, resolver=state_path)


def append_event(event: dict) -> None:
    append(_EVENTS, event, resolver=state_path)


def read_intents() -> list[dict]:
    return read_jsonl(_INTENTS, resolver=state_path)


def read_decisions() -> list[dict]:
    return read_jsonl(_DECISIONS, resolver=state_path)


def read_events() -> list[dict]:
    return read_jsonl(_EVENTS, resolver=state_path)


def intent_exists(source_proposal_id: str) -> bool:
    return any(i.get("source_proposal_id") == source_proposal_id for i in read_intents())
