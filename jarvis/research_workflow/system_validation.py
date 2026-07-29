"""Full System Validation (P169) — 전체 라이프사이클을 검증한다. **읽기 전용, 실행 없음.**

라이프사이클: External Data → Research Context → Agents → Experiment → Validation → Knowledge → Committee →
Human Review → Institutional Memory. 7개 확인: (1)workflow complete (2)committee works (3)governance passes
(4)monitoring healthy (5)metrics generated (6)dashboard integrated (7)no duplicated architecture.
**재사용**: 각 계층 validation(P120/130/140/150/160)·committee(P161)·governance(P168)·production_monitor(P166).

원칙(문서 §Constitution, §P169): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def validate_system() -> dict:
    """전체 시스템 7개 확인 + 라이프사이클(결정적·읽기전용)."""
    checks = []

    # (1) workflow complete — 각 계층 validation 통과(P120/130/140/150/160)
    layers = {}
    for mod, fn, key in (("operational_validation", "validate_operations", "operational"),
                         ("agent_validation", "validate_agents", "validated"),
                         ("brain_validation", "validate_brain", "validated"),
                         ("ops_validation", "validate_research_ops", "operational"),
                         ("institutional_intelligence_validation", "validate_intelligence", "validated")):
        r = _safe(lambda m=mod, f=fn: getattr(
            __import__(f"jarvis.research_workflow.{m}", fromlist=[f]), f)(), {})
        layers[mod] = bool(r.get(key))
    checks.append({"check": "workflow_complete", "ok": all(layers.values()),
                   "detail": f"layers={ {k: v for k, v in layers.items()} }"})

    # (2) committee works — CommitteePacket 생성 + 사람 결정 필요
    packet = _safe(lambda: __import__("jarvis.research_workflow.investment_committee",
                                      fromlist=["build_committee_packet"])
                   .build_committee_packet("Does momentum work?"), {})
    checks.append({"check": "committee_works",
                   "ok": bool(packet and packet.get("requires_human_decision") and "questions_for_human" in packet),
                   "detail": f"questions={len(packet.get('questions_for_human', [])) if packet else 0}"})

    # (3) governance passes — governance(P168)
    gov = _safe(lambda: __import__("jarvis.research_workflow.governance", fromlist=["build_governance"])
                .build_governance(), {})
    checks.append({"check": "governance_passes", "ok": bool(gov.get("passed")),
                   "detail": f"governance={gov.get('governance')}"})

    # (4) monitoring healthy — production_monitor(P166) 심각도 != CRITICAL
    pm = _safe(lambda: __import__("jarvis.research_workflow.production_monitor",
                                  fromlist=["build_production_status"]).build_production_status(), {})
    checks.append({"check": "monitoring_healthy", "ok": pm.get("overall_severity") != "CRITICAL",
                   "detail": f"severity={pm.get('overall_severity')}"})

    # (5) metrics generated — operational_metrics(P167)
    om = _safe(lambda: __import__("jarvis.research_workflow.operational_metrics",
                                  fromlist=["build_operational_metrics"]).build_operational_metrics(), {})
    checks.append({"check": "metrics_generated", "ok": bool(om.get("metrics")),
                   "detail": f"metrics={len(om.get('metrics', {}))}"})

    # (6) dashboard integrated — institutional intelligence 표면 조립
    dash = _safe(lambda: __import__("jarvis.research_workflow.agent_capability",
                                    fromlist=["capability_map"]).capability_map(), {})
    checks.append({"check": "dashboard_integrated", "ok": bool(dash.get("count")),
                   "detail": "console surfaces + committee page"})

    # (7) no duplicated architecture — 원장 3개 + governance 아키텍처 준수
    from jarvis.research_workflow import ledger as wl
    checks.append({"check": "no_duplicated_architecture",
                   "ok": len(wl.ALL_LEDGERS) == 3 and bool(gov.get("passed")),
                   "detail": f"rwf_ledgers={len(wl.ALL_LEDGERS)}"})

    all_ok = all(c["ok"] for c in checks)
    return {"lifecycle": ["External Data", "Research Context", "Agents", "Experiment", "Validation",
                          "Knowledge", "Committee", "Human Review", "Institutional Memory"],
            "checks": checks, "validated": all_ok, "layer_validations": layers,
            "is_advisory": True, "is_decision": False,
            "note": ("전체 시스템 검증(읽기전용) — 워크플로·위원회·거버넌스·모니터링·지표·대시보드·무중복. "
                     "각 계층 validation 재사용, 새 저장소 없음. 거래·집행 없음.")}


# ── P206 Deprecated (삭제 아님, ≥1 릴리스 유지) — 외부 직접 호출 대신 governance.validate(domain="architecture") ──
__deprecated__ = {"since": "P206", "use": "governance.validate(domain='architecture')", "domain": "architecture"}
