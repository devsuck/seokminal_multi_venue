"""Live Execution 원장 (P8.1) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

live_execution_requests.jsonl · live_execution_responses.jsonl · execution_audit_events.jsonl.
request_hash · response_hash 포함. 사람 게이트 전용·자율 트리거 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_REQUESTS = "live_execution_requests.jsonl"
_RESPONSES = "live_execution_responses.jsonl"
_EVENTS = "execution_audit_events.jsonl"


def append_request(row: dict) -> None:
    append(_REQUESTS, row, resolver=state_path)


def append_response(row: dict) -> None:
    append(_RESPONSES, row, resolver=state_path)


def append_event(row: dict) -> None:
    append(_EVENTS, row, resolver=state_path)


def read_requests() -> list[dict]:
    return read_jsonl(_REQUESTS, resolver=state_path)


def read_responses() -> list[dict]:
    return read_jsonl(_RESPONSES, resolver=state_path)


def read_events() -> list[dict]:
    return read_jsonl(_EVENTS, resolver=state_path)


def last_response() -> dict | None:
    rows = read_responses()
    return rows[-1] if rows else None


def request_exists(request_id: str) -> bool:
    return any(r.get("request_id") == request_id for r in read_requests())
