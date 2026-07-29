"""Execution Readiness 원장 (P7.7) — append-only. 삭제/재작성 없음. 소스 진실=JSONL.

execution_readiness_certificates.jsonl · execution_readiness_events.jsonl.
인증 산출물만. 집행 게이트웨이 무관·주문 없음·포지션 변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_CERTS = "execution_readiness_certificates.jsonl"
_EVENTS = "execution_readiness_events.jsonl"


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


def append_certificate(cert: dict) -> None:
    _append(_CERTS, cert)


def append_event(event: dict) -> None:
    _append(_EVENTS, event)


def read_certificates() -> list[dict]:
    return _read(_CERTS)


def read_events() -> list[dict]:
    return _read(_EVENTS)


def last_certificate() -> dict | None:
    rows = read_certificates()
    return rows[-1] if rows else None


def certificate_exists(certificate_id: str) -> bool:
    return any(c.get("certificate_id") == certificate_id for c in read_certificates())
