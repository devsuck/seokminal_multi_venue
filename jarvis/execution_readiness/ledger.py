"""Execution Readiness 원장 (P7.7) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

execution_readiness_certificates.jsonl · execution_readiness_events.jsonl.
인증 산출물만. 집행 게이트웨이 무관·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

from jarvis.config import state_path
from jarvis.ledger_io import append, read_jsonl

_CERTS = "execution_readiness_certificates.jsonl"
_EVENTS = "execution_readiness_events.jsonl"


def append_certificate(cert: dict) -> None:
    append(_CERTS, cert, resolver=state_path)


def append_event(event: dict) -> None:
    append(_EVENTS, event, resolver=state_path)


def read_certificates() -> list[dict]:
    return read_jsonl(_CERTS, resolver=state_path)


def read_events() -> list[dict]:
    return read_jsonl(_EVENTS, resolver=state_path)


def last_certificate() -> dict | None:
    rows = read_certificates()
    return rows[-1] if rows else None


def certificate_exists(certificate_id: str) -> bool:
    return any(c.get("certificate_id") == certificate_id for c in read_certificates())
