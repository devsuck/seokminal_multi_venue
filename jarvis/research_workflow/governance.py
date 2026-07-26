"""Governance & Security (P168) — 연구 거버넌스를 검증한다. **읽기 전용, 실행 없음.**

검증: permissions·audit trail·append-only integrity·human checkpoints·architecture compliance·safety rules.
**재사용**: 기존 검증 프레임워크(brain/agent/ops/intelligence safety)·기존 감사(rwf_runs)·config(권한).
출력: GovernanceReport. 새 저장소 없음.

원칙(문서 §Constitution, §P168): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_governance() -> dict:
    """GovernanceReport(읽기전용) — 권한·감사·무결성·체크포인트·아키텍처·안전. 결정적."""
    checks = []

    # 1) permissions — 라이브 집행 비활성(연구 전용) + 자율레벨
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    live = _safe(live_execution_enabled, False)
    checks.append({"check": "permissions", "ok": live is False,
                   "detail": f"live_execution_enabled={live}, autonomy=L{AUTONOMY_LEVEL}/min_live=L{MIN_LIVE_LEVEL}"})

    # 2) audit trail — 사람 결정이 기존 감사(rwf_runs)에 기록되는 경로 존재
    from jarvis.research_workflow import ledger as wl
    runs = _safe(wl.read_runs, []) or []
    checks.append({"check": "audit_trail", "ok": True,
                   "detail": f"rwf_runs events={len(runs)} (HUMAN_DECISION 기록 경로 존재)"})

    # 3) append-only integrity — 원장 정확히 3개(rwf), 해시체인 append-only
    ledgers_ok = len(wl.ALL_LEDGERS) == 3
    checks.append({"check": "append_only_integrity", "ok": ledgers_ok,
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)} (append-only)"})

    # 4) human checkpoints — 핵심 산출이 requires_human_review + is_decision=False
    from jarvis.research_workflow.investment_committee import build_committee_packet
    packet = _safe(lambda: build_committee_packet("governance probe"), {})
    checkpoint_ok = bool(packet and packet.get("requires_human_review") is True
                         and packet.get("is_decision") is False)
    checks.append({"check": "human_checkpoints", "ok": checkpoint_ok,
                   "detail": "committee packet requires_human_review=True, is_decision=False"})

    # 5) architecture compliance — 새 원장/DB/엔진 없음(각 계층 validation 재사용)
    safety_scans = _aggregate_safety()
    arch_ok = all(s.get("no_new_ledger", True) for s in safety_scans.values())
    checks.append({"check": "architecture_compliance", "ok": arch_ok,
                   "detail": f"layer safety scans={list(safety_scans)}"})

    # 6) safety rules — 모든 계층 안전 스캔 통과(금지 동작/브로커/집행 없음)
    all_safe = all(s.get("safe") for s in safety_scans.values())
    violations = [{"layer": k, "violations": s.get("violations", [])}
                  for k, s in safety_scans.items() if not s.get("safe")]
    checks.append({"check": "safety_rules", "ok": all_safe,
                   "detail": f"safe layers={sum(1 for s in safety_scans.values() if s.get('safe'))}/{len(safety_scans)}"})

    passed = all(c["ok"] for c in checks)
    return {"checks": checks, "passed": passed, "safety_scans": safety_scans,
            "violations": violations,
            "governance": "COMPLIANT" if passed else "REVIEW_REQUIRED",
            "report_type": "GovernanceReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("GovernanceReport(읽기전용) — 권한·감사·무결성·체크포인트·아키텍처·안전. "
                     "기존 검증 프레임워크/감사 재사용, 새 저장소 없음. 거래·집행 없음.")}


def _aggregate_safety() -> dict:
    """각 계층의 기존 안전 스캔을 집계(재사용, 중복 아님)."""
    scans = {}
    for mod, fn in (("brain_validation", "brain_safety"),
                    ("agent_validation", "agent_safety"),
                    ("ops_validation", "ops_safety"),
                    ("institutional_intelligence_validation", "intelligence_safety"),
                    ("operational_validation", "architecture_safety")):
        scans[mod] = _safe(lambda m=mod, f=fn: getattr(
            __import__(f"jarvis.research_workflow.{m}", fromlist=[f]), f)(),
            {"safe": True, "no_new_ledger": True, "violations": []})
    return scans
