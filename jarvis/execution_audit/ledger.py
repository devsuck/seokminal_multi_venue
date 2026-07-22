"""Execution Audit 원장 (P8.6) — append-only 해시체인. 삭제/재작성 없음. 진실=JSONL.

execution_audit_certificates.jsonl. 각 인증서: certificate_id·certificate_hash·
previous_hash·timestamp. 증명 기록만 — 주문/집행/브로커/상태변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

_CERTS = "execution_audit_certificates.jsonl"


def append_certificate(cert: dict) -> None:
    p = state_path(_CERTS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(cert, ensure_ascii=False, default=str) + "\n")


def read_certificates() -> list[dict]:
    p = state_path(_CERTS)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def certificate_exists(certificate_id: str) -> bool:
    return any(c.get("certificate_id") == certificate_id for c in read_certificates())


def chain_head() -> dict | None:
    certs = read_certificates()
    return certs[-1] if certs else None


def last_certificate() -> dict | None:
    return chain_head()
