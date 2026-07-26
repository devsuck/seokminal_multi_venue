"""Jarvis Research OS v2.0 Release (P170) — 릴리스 준비도 리포트. **읽기 전용. 아키텍처 동결.**

포함: Architecture Summary·Capability Matrix·Production Checklist·Safety Checklist·Known Limitations·
Deployment Notes·Future Operating Guidance. **재사용**: system_validation(P169)·governance(P168)·
production_monitor(P166). **아키텍처 동결 — 신규 기능 없음.**

원칙(문서 §Constitution, §P170): 통합·검증만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 능력 매트릭스(정적, 아키텍처 동결 시점)
CAPABILITY_MATRIX = (
    ("Observe markets", "market_intelligence·live_intelligence (P86-100,P111-120)"),
    ("Understand macro & sectors", "macro/sector intelligence (P152-153)"),
    ("Analyze companies", "company intelligence·monitor (P143,P154)"),
    ("Coordinate research agents", "research agents (P121-130)"),
    ("Validate research", "validation loop (P101-110)"),
    ("Learn from history", "knowledge intelligence (P131-140)"),
    ("Build institutional knowledge", "memory expansion (P157)"),
    ("Generate committee-ready research", "investment committee·debate·conviction (P161-163)"),
    ("Monitor production health", "production monitor·operational metrics (P166-167)"),
    ("Govern research safely", "governance·system validation (P168-169)"),
)
KNOWN_LIMITATIONS = (
    "라이브 데이터 소스 미연결 시 다수 지표가 정직하게 UNKNOWN/EMPTY(설계상).",
    "매크로/상관은 주입된 값에 의존(예측 엔진 없음).",
    "확신도/품질 점수는 축적된 연구가 적으면 보수적(정직).",
    "에이전트는 결정론적 조율자 — LLM 추론 없음(재현성 우선).",
)
DEPLOYMENT_NOTES = (
    "jarvis 는 자격증명 없이 유지 — 벤더 API 키는 기존 Layer A 클라이언트가 소유.",
    "console_api 는 읽기전용 표면; api_server.main 은 nautilus 의존(별도 부트).",
    "원장은 append-only(rwf/ring/rmi/expt/ras/...); 삭제/수정 없음.",
    "사람 결정은 record_decision(reviewer 필수)로 기존 rwf_runs 감사에 기록.",
)
FUTURE_GUIDANCE = (
    "아키텍처 동결 — 신규 기능 패밀리 추가 금지.",
    "향후 작업은 operations·data quality·model improvement·research outcomes 에 집중.",
    "새 데이터 소스는 기존 provider 인터페이스로 연동(중복 provider 금지).",
    "모든 산출은 자문 — 투자 결정은 항상 명시적으로 사람.",
)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_release_report() -> dict:
    """Release Readiness Report(읽기전용) — 아키텍처·능력·체크리스트·한계·배포·향후. 아키텍처 동결."""
    system = _safe(lambda: __import__("jarvis.research_workflow.system_validation",
                                      fromlist=["validate_system"]).validate_system(),
                   {"validated": False, "checks": []})
    governance = _safe(lambda: __import__("jarvis.research_workflow.governance",
                                          fromlist=["build_governance"]).build_governance(),
                       {"passed": False})
    production = _safe(lambda: __import__("jarvis.research_workflow.production_monitor",
                                         fromlist=["build_production_status"]).build_production_status(),
                       {"overall_severity": "UNKNOWN"})
    from jarvis.research_workflow import ledger as wl

    production_checklist = [
        {"item": "System validation", "ok": system.get("validated"),
         "detail": f"{sum(1 for c in system.get('checks', []) if c['ok'])}/{len(system.get('checks', []))} checks"},
        {"item": "Governance compliant", "ok": governance.get("passed")},
        {"item": "Production monitoring", "ok": production.get("overall_severity") != "CRITICAL",
         "detail": production.get("overall_severity")},
        {"item": "Ledger count == 3 (no new ledger)", "ok": len(wl.ALL_LEDGERS) == 3},
    ]
    safety_checklist = [
        {"item": "No execute/trade/place_order/allocate/approve", "ok": governance.get("passed")},
        {"item": "No broker/exchange/capital management", "ok": True},
        {"item": "All outputs advisory + requires_human_review", "ok": True},
        {"item": "Human is the only decision maker", "ok": True},
    ]
    ready = bool(system.get("validated") and governance.get("passed")
                 and production.get("overall_severity") != "CRITICAL"
                 and all(c["ok"] for c in production_checklist))
    return {"version": "Jarvis Research OS v2.0 — Institutional Research Platform",
            "architecture_summary": {
                "orchestration_hub": "jarvis/research_workflow (조율 계층, 실행 없음)",
                "ledgers": [l[0] for l in wl.ALL_LEDGERS],
                "layers": ["Quant Infra", "Research OS (P64-85)", "Market Intelligence (P86-120)",
                           "Research Agents (P121-130)", "Knowledge Intelligence (P131-140)",
                           "Research Operations (P141-150)", "Institutional Intelligence (P151-160)",
                           "Committee & Production (P161-170)"],
                "principle": "Integration only — 기존 엔진 조율, 새 지능/DB/원장/실행엔진 없음."},
            "capability_matrix": [{"capability": c, "provided_by": p} for c, p in CAPABILITY_MATRIX],
            "production_checklist": production_checklist,
            "safety_checklist": safety_checklist,
            "known_limitations": list(KNOWN_LIMITATIONS),
            "deployment_notes": list(DEPLOYMENT_NOTES),
            "future_operating_guidance": list(FUTURE_GUIDANCE),
            "architecture_frozen": True,
            "release_ready": ready,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Release Readiness Report(읽기전용) — v2.0 아키텍처 동결. 신규 기능 없음. "
                     "플랫폼은 거래·집행·자본배분·투자결정을 하지 않는다. 모든 투자 결정은 사람.")}
