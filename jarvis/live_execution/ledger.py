"""Live Execution 원장 (P8.1) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

live_execution_requests.jsonl · live_execution_responses.jsonl · execution_audit_events.jsonl.
request_hash · response_hash 포함. 사람 게이트 전용·자율 트리거 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_REQUESTS = "live_execution_requests.jsonl"
_RESPONSES = "live_execution_responses.jsonl"
_EVENTS = "execution_audit_events.jsonl"


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


def append_request(row: dict) -> None:
    _append(_REQUESTS, row)


def append_response(row: dict) -> None:
    _append(_RESPONSES, row)


def append_event(row: dict) -> None:
    _append(_EVENTS, row)


def read_requests() -> list[dict]:
    return _read(_REQUESTS)


def read_responses() -> list[dict]:
    return _read(_RESPONSES)


def read_events() -> list[dict]:
    return _read(_EVENTS)


def last_response() -> dict | None:
    rows = read_responses()
    return rows[-1] if rows else None


def request_exists(request_id: str) -> bool:
    return any(r.get("request_id") == request_id for r in read_requests())
