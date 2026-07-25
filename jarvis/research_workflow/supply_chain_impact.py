"""Supply Chain Intelligence Expansion (P99) — 기존 공급망 그래프를 **영향 전파 엔진**으로. **읽기 전용.**

TSMC production issue → Apple → NVIDIA → AI Server → Power Infra. 매 이벤트마다 직접 공급자/고객/경쟁사/
관련 섹터를 찾고 Supply Chain Impact Report(영향 개체·관계 경로·과거 사건·불확실성)를 만든다.
**기존 그래프 인프라(event_intelligence relationship graph) 재사용 — 또 다른 그래프 DB를 만들지 않는다.**
참조 그래프는 몇 개 엣지를 보강(정적 참조 데이터, 저장소 아님).

원칙(문서 §Constitution, §P99): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 기존 관계 kind → 관계 범주(결정적 매핑)
_REL_CATEGORY = {
    "fab_supplier": "supplier", "equipment_supplier": "supplier", "assembler": "supplier",
    "hosts": "location", "etf_member": "sector", "correlated_with": "peer",
    "macro_driver": "macro", "component_of": "customer", "customer_of": "customer",
    "competitor_of": "competitor",
}
# 참조 그래프 보강(정적, 저장소 아님) — AI 서버·전력 인프라 확장
_EXTRA_RELATIONSHIPS = (
    ("NVIDIA", "AI_Server", "component_of"),
    ("AMD", "AI_Server", "component_of"),
    ("AI_Server", "Power_Infra", "customer_of"),
    ("AI_Server", "SMH", "etf_member"),
    ("TSMC", "Samsung", "competitor_of"),
)


def _engine():
    from jarvis.research_assistant.event_intelligence import DEFAULT_RELATIONSHIPS, MarketEventIntelligence
    return MarketEventIntelligence(relationships=list(DEFAULT_RELATIONSHIPS) + list(_EXTRA_RELATIONSHIPS))


def propagate(event, *, max_depth: int = 4, assistant=None) -> dict:
    """이벤트 → 공급망 영향 리포트(직접 공급자/고객/경쟁사/섹터 + 경로 + 과거 + 불확실성). 결정적."""
    mei = _engine()
    imp = mei.analyze_event(event if isinstance(event, dict) else {"text": str(event)},
                            max_depth=max_depth)
    if not imp.origin:
        return {"origin": "", "affected_entities": [], "note": "알려진 개체를 찾지 못함 — 참조 그래프 확장 필요.",
                "is_advisory": True, "is_decision": False}

    # 관계 kind → 범주로 분류(직접 공급자/고객/경쟁사/섹터)
    rel_of: dict = {}
    for e in imp.impact_chain.get("edges", []):
        rel_of.setdefault(e["target"], _REL_CATEGORY.get(e["kind"], "related"))
    categorized = {"supplier": [], "customer": [], "competitor": [], "sector": [], "related": [],
                   "location": [], "peer": [], "macro": []}
    affected = []
    for cand in imp.candidates:
        cat = rel_of.get(cand.entity, "related")
        categorized.setdefault(cat, []).append(cand.entity)
        # 불확실성 = 거리에 따라 증가(직접=낮음)
        uncertainty = "LOW" if cand.distance <= 1 else "MEDIUM" if cand.distance == 2 else "HIGH"
        affected.append({"entity": cand.entity, "category": cat, "distance": cand.distance,
                         "relationship_path": cand.path, "uncertainty": uncertainty})

    # 과거 사건 — recall 재사용
    historical = {}
    try:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine()
        r = assistant.recall(imp.origin)
        historical = {"origin": imp.origin, "prior_records": r.total_hits}
    except Exception:  # noqa: BLE001
        pass

    return {"origin": imp.origin, "affected_entities": affected,
            "direct_suppliers": categorized["supplier"], "customers": categorized["customer"],
            "competitors": categorized["competitor"], "related_sectors": categorized["sector"],
            "relationship_graph": imp.impact_chain, "historical_events": historical,
            "uncertainty_note": "거리가 멀수록 영향 불확실성 증가 — 사람 검토 필요.",
            "is_advisory": True, "is_decision": False,
            "note": "기존 공급망 그래프 재사용 영향 전파(읽기전용) — 새 그래프 DB 없음, 신호 아님."}


def relationship_graph() -> dict:
    """확장 참조 그래프 뷰(읽기전용)."""
    return _engine().relationship_graph()
