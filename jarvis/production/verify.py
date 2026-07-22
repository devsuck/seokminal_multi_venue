"""Production 검증 (P6.1) — 게이트 결정 결정성 + 경계 닫힘 확인. 소스 무변경."""
from __future__ import annotations

from jarvis.production.gate import ProductionGate
from jarvis.production.models import ProductionProposal


def verify(now: str = "2026-07-22T00:00:00Z") -> dict:
    # 고정 합성 제안 → 게이트 두 번 → 동일 결정(결정적)
    prop = ProductionProposal(proposal_id="PP:verify", source="verify",
                              strategy="__nonexistent__", created_at=now)
    g = ProductionGate()
    d1 = g.check(prop, now, ts="verify")
    d2 = g.check(prop, now, ts="verify")
    deterministic = (d1.decision == d2.decision and d1.failed_checks == d2.failed_checks)
    return {
        "ok": bool(deterministic and d1.decision == "BLOCK"),
        "deterministic": deterministic,
        "boundary_closed": d1.decision == "BLOCK",
        "decision": d1.decision,
        "failed_checks": d1.failed_checks,
    }
