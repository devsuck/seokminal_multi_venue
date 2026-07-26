"""Company Intelligence Graph (P154) — 기업 이해를 확장한다. **읽기 전용, 매수/매도 신호 없음.**

**재사용**: knowledge_graph·company_monitor(P143)·fundamental_pipeline·supply_chain_impact(관계 전파).
추적: company·suppliers·customers·competitors·industries·events. 출력: CompanyIntelligenceReport
{entity, relationships, events, financial_context, historical_lessons, risks}. 새 저장소 없음.

원칙(문서 §Constitution, §P154): 통합·조율만. 결정적. 거래·집행·신호 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def analyze_company(entity: str, *, financials=None, headlines=None, transactions=None,
                    assistant=None) -> dict:
    """기업 → CompanyIntelligenceReport(관계·이벤트·재무·과거교훈·리스크). 결정적·읽기전용."""
    name = (entity or "").strip()

    # 1) 관계(공급자/고객/경쟁사/섹터) — supply_chain_impact 재사용
    prop = _safe(lambda: __import__("jarvis.research_workflow.supply_chain_impact", fromlist=["propagate"])
                 .propagate({"entity": name, "text": f"{name} company"}), {})
    relationships = {"suppliers": prop.get("direct_suppliers", []),
                     "customers": prop.get("customers", []),
                     "competitors": prop.get("competitors", []),
                     "related_sectors": prop.get("related_sectors", []),
                     "affected_entities": prop.get("affected_entities", [])[:10]}

    # 2) 이벤트·재무 — company_monitor(P143) 재사용
    monitor = _safe(lambda: __import__("jarvis.research_workflow.company_monitor", fromlist=["update"])
                    .update(name, financials=financials, headlines=headlines,
                            transactions=transactions, assistant=assistant), {})
    financial_context = {"earnings": monitor.get("earnings", []),
                         "impact": monitor.get("impact", {}),
                         "fundamentals": (monitor.get("competitive_position", []))}

    # 3) 과거 교훈 — semantic_recall 재사용
    ctx = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall", fromlist=["recall_context"])
                .recall_context(name, assistant=assistant), {})
    historical_lessons = {"similar_failures": ctx.get("similar_failures", []),
                          "past_conclusions": ctx.get("past_conclusions", []),
                          "prior_research": ctx.get("prior_research_count", 0)}

    # 4) 리스크(결정적) — 관계 집중 + 과거 실패 + 이벤트 영향
    risks = []
    if len(relationships["customers"]) <= 1 and relationships["suppliers"]:
        risks.append("고객 집중 — 수요 충격 취약")
    if relationships["competitors"]:
        risks.append(f"경쟁: {', '.join(relationships['competitors'][:3])}")
    if ctx.get("made_this_mistake"):
        risks.append("과거 동일 연구 실패 이력 — 가정 재검토")
    if monitor.get("impact", {}).get("direction") == "NEGATIVE":
        risks.append("최근 부정적 실적/이벤트")
    risks = risks or ["표준 기업 리스크 — 펀더멘털/레짐 확인"]

    return {"entity": name or "unknown", "relationships": relationships,
            "industries": relationships["related_sectors"],
            "events": monitor.get("events", []),
            "financial_context": financial_context,
            "historical_lessons": historical_lessons,
            "research_priority": monitor.get("research_priority"),
            "risks": risks,
            "report_type": "CompanyIntelligenceReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "is_trade_signal": False,
            "note": ("CompanyIntelligenceReport(읽기전용) — 관계·이벤트·재무·교훈·리스크. 매수/매도 신호 아님. "
                     "knowledge_graph/company_monitor/fundamental/supply_chain 재사용, 새 저장소 없음.")}
