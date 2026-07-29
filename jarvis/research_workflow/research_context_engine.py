"""Research Context Engine (P155) — 모든 인텔리전스를 **하나의 연구 컨텍스트**로 결합한다. **읽기 전용.**

입력: market state·macro state·sector·company·historical memory·past failures. 출력: ResearchContextPackage
{Question, Current Environment, Historical Similar Cases, Relevant Companies, Relevant Strategies,
Known Risks, Contradictions, Missing Evidence}. **재사용**: semantic_recall(P133)·knowledge_graph(P132)·
conflict_detection(P135)·macro/sector/company intelligence(P152-154). 새 저장소 없음.

원칙(문서 §Constitution, §P155): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_research_context(question: str, *, entity: str = "", sector: str = "",
                           macro: dict | None = None, market: dict | None = None,
                           assistant=None) -> dict:
    """질문 + 환경 → ResearchContextPackage(8개 섹션). 모든 인텔리전스 결합. 결정적·읽기전용."""
    q = (question or "").strip()

    # 회수(경험·유사실패·과거결론·모순) — semantic_recall
    recall = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall", fromlist=["recall_context"])
                   .recall_context(q, assistant=assistant), {})
    # 매크로 환경 — macro_intelligence
    macro_ctx = _safe(lambda: __import__("jarvis.research_workflow.macro_intelligence",
                                         fromlist=["build_macro_context"])
                      .build_macro_context(indicators=macro or {}, assistant=assistant), {})
    # 레짐 — regime
    regime = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"])
                   .detect_regime(market or {}, assistant=assistant), {"regime": "UNKNOWN"})
    # 지식 그래프(관련 기업/전략 노드) — knowledge_graph_upgrade
    graph = _safe(lambda: __import__("jarvis.research_workflow.knowledge_graph_upgrade",
                                     fromlist=["build_research_knowledge_graph"])
                  .build_research_knowledge_graph(q or entity, limit=60), {"nodes": []})
    companies = [n["label"] for n in graph.get("nodes", []) if n["type"] in ("Sector", "MacroEvent")][:10]
    strategies = [n["label"] for n in graph.get("nodes", []) if n["type"] == "Strategy"][:10]
    # 섹터 리스크(있으면) — sector_intelligence
    sector_ctx = {}
    if sector:
        sector_ctx = _safe(lambda: __import__("jarvis.research_workflow.sector_intelligence",
                                              fromlist=["analyze_sector"])
                           .analyze_sector(sector, assistant=assistant), {})
    # 기업 리스크(있으면) — company_intelligence
    company_ctx = {}
    if entity:
        company_ctx = _safe(lambda: __import__("jarvis.research_workflow.company_intelligence",
                                               fromlist=["analyze_company"])
                            .analyze_company(entity, assistant=assistant), {})
    # 모순 — conflict_detection
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(topic=q),
                      {"conflicts": []})

    known_risks = (sector_ctx.get("risk_factors", []) + company_ctx.get("risks", []) +
                   ([f"macro: {macro_ctx.get('macro_state')}"] if macro_ctx.get("macro_state") not in
                    (None, "UNKNOWN") else []))
    missing = recall.get("missing_evidence", []) if isinstance(recall.get("missing_evidence"), list) else []
    if not recall.get("prior_research_count"):
        missing = missing + ["과거 유사 연구 부족 — 근거 축적 필요"]

    return {"question": q,
            "package": {
                "1_question": q,
                "2_current_environment": {"regime": regime.get("regime"),
                                          "macro_state": macro_ctx.get("macro_state"),
                                          "macro_uncertainty": macro_ctx.get("uncertainty"),
                                          "affected_assets": macro_ctx.get("affected_assets", [])},
                "3_historical_similar_cases": {"past_conclusions": recall.get("past_conclusions", []),
                                               "prior_research": recall.get("prior_research_count", 0),
                                               "tried_before": recall.get("tried_before", False)},
                "4_relevant_companies": companies or ([entity] if entity else []),
                "5_relevant_strategies": strategies,
                "6_known_risks": known_risks or ["표준 리스크 — 레짐/표본 확인"],
                "7_contradictions": conflicts.get("conflicts", [])[:5],
                "8_missing_evidence": missing,
            },
            "is_context_package": True, "requires_human_review": True,
            "is_advisory": True, "is_decision": False,
            "note": ("ResearchContextPackage(읽기전용) — 8섹션(질문·환경·과거·기업·전략·리스크·모순·누락). "
                     "semantic_recall/knowledge_graph/conflict/macro/sector/company 결합, 새 저장소 없음.")}
