"""Execution Audit 검증 (P8.6) — 해시체인 무결성·결정적 재현·중복 탐지. 읽기전용.

verify_chain: 각 인증서 previous_hash == 직전 certificate_hash. replay: 동일입력 재감사 동일.
**어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.execution_audit import ledger
from jarvis.execution_audit.models import GENESIS


def verify_chain() -> dict:
    certs = ledger.read_certificates()
    if not certs:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    seen = set()
    for i, c in enumerate(certs):
        if c.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not c.get("certificate_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_certificate_hash"}
        if c.get("certificate_id") in seen:
            return {"ok": False, "broken_at": i, "reason": "duplicate_certificate_id"}
        seen.add(c.get("certificate_id"))
        prev = c["certificate_hash"]
    return {"ok": True, "n": len(certs), "reason": "chain_intact"}


def replay(engine, request_id: str, now: str = "", **sources) -> dict:
    """동일 입력 재감사 → 동일 certificate_hash(결정성 확인)."""
    c1 = engine.audit(request_id, now, **sources)
    c2 = engine.audit(request_id, now, **sources)
    return {"deterministic": c1.certificate_hash == c2.certificate_hash
            and c1.to_dict() == c2.to_dict(),
            "certificate_hash": c1.certificate_hash, "audit_status": c1.audit_status}
