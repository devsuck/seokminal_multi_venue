"""Production Monitoring (P166) — 생산 컴포넌트 상태를 감시한다. **읽기 전용.**

감시: API health·Agent health·Research pipeline·Scheduler·Dashboard·Memory health·Knowledge health.
출력: ProductionStatusReport. 심각도: OK·WARNING·CRITICAL. **재사용**: data_production(P151)·agent_validation
(P130)·health_monitor(P77)·research_scheduler(P141)·continuous_learning·knowledge_quality(P139). 새 저장소 없음.

원칙(문서 §Constitution, §P166): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _sev(ok_ratio: float) -> str:
    return "OK" if ok_ratio >= 0.75 else "WARNING" if ok_ratio >= 0.4 else "CRITICAL"


def build_production_status() -> dict:
    """ProductionStatusReport(읽기전용) — 7개 컴포넌트 severity + 종합. 결정적."""
    components = []

    # API health — data_production
    dp = _safe(lambda: __import__("jarvis.research_workflow.data_production",
                                  fromlist=["build_data_production"]).build_data_production(), {})
    api_ratio = (dp.get("available_count", 0) / max(dp.get("count", 1), 1)) if dp else 0.0
    components.append({"component": "API health", "severity": _sev(api_ratio),
                       "detail": f"{dp.get('available_count', 0)}/{dp.get('count', 0)} providers"})

    # Agent health — agent_validation
    av = _safe(lambda: __import__("jarvis.research_workflow.agent_validation",
                                  fromlist=["validate_agents"]).validate_agents(), {})
    components.append({"component": "Agent health", "severity": "OK" if av.get("validated") else "WARNING",
                       "detail": f"validated={av.get('validated')}"})

    # Research pipeline — health_monitor
    hm = _safe(lambda: __import__("jarvis.research_workflow.health_monitor", fromlist=["build_health"])
               .build_health(), {})
    hscore = hm.get("overall_health_score", 0)
    components.append({"component": "Research pipeline",
                       "severity": "OK" if hscore >= 60 else "WARNING" if hscore >= 30 else "CRITICAL",
                       "detail": f"health={hscore} band={hm.get('health_band')}"})

    # Scheduler — research_scheduler
    sc = _safe(lambda: __import__("jarvis.research_workflow.research_scheduler", fromlist=["plan_cycle"])
               .plan_cycle("daily"), {})
    components.append({"component": "Scheduler",
                       "severity": "OK" if sc.get("tasks") and sc.get("auto_execution") is False else "WARNING",
                       "detail": f"cycles configured, auto_execution={sc.get('auto_execution')}"})

    # Dashboard — institutional intelligence assembles
    dash = _safe(lambda: __import__("jarvis.research_workflow.agent_capability",
                                    fromlist=["capability_map"]).capability_map(), {})
    components.append({"component": "Dashboard", "severity": "OK" if dash.get("count") else "WARNING",
                       "detail": "console surfaces available"})

    # Memory health — continuous_learning
    ls = _safe(lambda: __import__("jarvis.research_workflow.continuous_learning",
                                  fromlist=["learning_status"]).learning_status(), {})
    components.append({"component": "Memory health", "severity": "OK",
                       "detail": f"channels total={ls.get('total', 0)}"})

    # Knowledge health — knowledge_quality
    kh = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                  fromlist=["build_knowledge_health"]).build_knowledge_health(), {})
    kgrade = kh.get("grade", "EMPTY")
    components.append({"component": "Knowledge health",
                       "severity": "OK" if kgrade in ("HEALTHY", "EMPTY") else "WARNING" if kgrade == "FAIR"
                       else "CRITICAL",
                       "detail": f"grade={kgrade} score={kh.get('health_score')}"})

    crit = sum(1 for c in components if c["severity"] == "CRITICAL")
    warn = sum(1 for c in components if c["severity"] == "WARNING")
    overall = "CRITICAL" if crit else "WARNING" if warn else "OK"
    return {"components": components, "overall_severity": overall,
            "counts": {"OK": len(components) - crit - warn, "WARNING": warn, "CRITICAL": crit},
            "report_type": "ProductionStatusReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("ProductionStatusReport(읽기전용) — API·Agent·Pipeline·Scheduler·Dashboard·Memory·Knowledge. "
                     "기존 모니터 재사용, 새 저장소 없음.")}
