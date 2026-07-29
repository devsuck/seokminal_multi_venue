"""Release Gate (P40) — v1.0 RC 릴리스 게이트: 무결성·보안·준비성·재현·의존성 집계 검증. **실행 없음.**

기존 검증 계층(P35 통합·P38 보안·P39 준비성)을 집계해 릴리스 게이트를 판정한다. 상위 계층은 READ ONLY.
"""
from __future__ import annotations


def check_system_integrity(now="2026-07-24T00:00:00Z") -> dict:
    """P35 전체 계층 정적 검증."""
    from jarvis.system_integration.engine import SystemIntegrationEngine
    res = SystemIntegrationEngine().run_full_validation("RELEASE", now, commit=False)
    return {"gate": "system_integrity", "ok": res["all_passed"],
            "checks": res["validation"]["checks_run"], "failed": res["validation"]["checks_failed"]}


def check_security_audit(now="2026-07-24T00:00:00Z") -> dict:
    """P38 전체 보안 감사."""
    from jarvis.security_audit.engine import SecurityAuditEngine
    res = SecurityAuditEngine().run_full_audit("RELEASE", now, commit=False)
    return {"gate": "security_audit", "ok": res["all_secure"],
            "targets": res["audit"]["targets"], "failed": res["audit"]["checks_failed"]}


def check_production_readiness() -> dict:
    """P39 준비성 평가."""
    from jarvis.production_review.assess import run_readiness_assessment
    res = run_readiness_assessment()
    return {"gate": "production_readiness", "ok": res["ready"],
            "deployment_performed": res["deployment_performed"]}


def check_replay_validation(now="2026-07-24T00:00:00Z") -> dict:
    """재현 검증: 검증 계층 replay 결정성."""
    from jarvis.system_integration.engine import SystemIntegrationEngine
    from jarvis.system_integration.verify import replay as si_replay
    from jarvis.security_audit.engine import SecurityAuditEngine
    from jarvis.security_audit.verify import replay as sc_replay
    si = si_replay(SystemIntegrationEngine(), now)["deterministic"]
    sc = sc_replay(SecurityAuditEngine(), now)["deterministic"]
    return {"gate": "replay_validation", "ok": si and sc}


def check_dependency_validation() -> dict:
    """의존성 검증: 순환 없음(단방향 상위 참조)."""
    from jarvis.architecture_docs.validate import check_no_dependency_violations
    return {"gate": "dependency_validation", "ok": check_no_dependency_violations()["ok"]}


def run_release_gate(now="2026-07-24T00:00:00Z") -> dict:
    """전체 릴리스 게이트(5단계). 모두 통과해야 RC 승인. **검증만 — 실행/배포 없음.**"""
    gates = [check_system_integrity(now), check_security_audit(now),
             check_production_readiness(), check_replay_validation(now),
             check_dependency_validation()]
    return {"approved": all(g["ok"] for g in gates), "gates": gates,
            "live_execution": False, "autonomous_trading": False}
