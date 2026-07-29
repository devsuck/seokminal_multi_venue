"""Intelligent Experiment Prioritization (P174) — 다음에 **검토할** 실험을 결정한다. **추천만, 결정 없음.**

기존 research_prioritizer(P76, 7요인)를 재사용하고 3개 요인을 **추가**한다:
  validation_complexity(필요검증 수)·research_coverage(지식그래프 커버리지)·knowledge_gaps(빈 영역).
합성 스코어로 최종 순위 → 사람이 다음에 볼 실험을 추천(자문). **새 스코어러 없음 — 기존 확장.**

원칙(문서 §Constitution, §P174): 통합·조율만 · 결정적 · 추천만 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

# 추가 요인 가중(기존 합성 스코어 위에 얹는 조정치, 결정적)
_EXTRA_W = {"validation_complexity": 0.10, "research_coverage": 0.08, "knowledge_gap": 0.10}
_BASE_VALIDATION_MAX = 6.0


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _base_ranked(candidates):
    def _go():
        from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
        return ResearchPrioritizer().prioritize(candidates).to_dict()
    return _safe(_go, {"items": [], "recommended": {}})


def _coverage_index():
    """지식그래프 커버리지 대략치(노드/엣지 밀도) — research_coverage/knowledge_gap 산출용."""
    kg = _safe(lambda: __import__("jarvis.research_workflow.knowledge_graph_upgrade",
                                  fromlist=["build_research_knowledge_graph"]
                                  ).build_research_knowledge_graph(), {}) or {}
    nodes = int(kg.get("node_count") or len(kg.get("nodes", []) or []))
    edges = int(kg.get("edge_count") or len(kg.get("edges", []) or []))
    # 커버리지 = 밀도 근사(0~1). 빈약할수록 knowledge_gap 큼.
    coverage = round(min(1.0, edges / max(1, nodes * 4)), 4) if nodes else 0.0
    return coverage, nodes, edges


def _validation_complexity(item):
    """필요검증 수 → 복잡도(0~1). 복잡할수록 정보가치 조정에 반영."""
    req = item.get("required_validation")
    if isinstance(req, list) and req:
        return round(min(1.0, len(req) / _BASE_VALIDATION_MAX), 4)
    return 0.5


def prioritize_experiments(candidates=None, *, topic: str = "", limit: int = 10) -> dict:
    """후보 실험 → 확장 요인 순위(자문). candidates 없으면 continuous_queue 에서 취득. 결정적·읽기전용."""
    if candidates is None:
        candidates = _safe(lambda: __import__("jarvis.research_workflow.continuous_queue",
                                              fromlist=["build_continuous_queue"]
                                              ).build_continuous_queue(topic=topic).get("backlog", []),
                           []) or []
    candidates = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in candidates]

    base = _base_ranked(candidates)
    coverage, nodes, edges = _coverage_index()
    knowledge_gap = round(1.0 - coverage, 4)

    ranked = []
    for it in base.get("items", []):
        item = dict(it)
        base_score = float(item.get("score", 0.0))
        vc = _validation_complexity(item)
        # 복잡도는 정보가치를 약간 높이되(도전적), 커버리지 낮은 영역(gap 큰)을 우대
        adj = (_EXTRA_W["validation_complexity"] * (1.0 - vc)      # 단순할수록 착수 쉬움
               + _EXTRA_W["research_coverage"] * coverage
               + _EXTRA_W["knowledge_gap"] * knowledge_gap)
        composite = round(base_score + adj, 4)
        factors = dict(item.get("scores", {}))
        factors.update({"validation_complexity": vc, "research_coverage": coverage,
                        "knowledge_gap": knowledge_gap})
        ranked.append({"hypothesis_id": item.get("hypothesis_id", ""),
                       "statement": item.get("statement", ""), "source": item.get("source", ""),
                       "base_score": base_score, "composite_score": composite, "factors": factors,
                       "requires_human_review": True, "is_advisory": True, "is_decision": False})

    ranked.sort(key=lambda x: (-x["composite_score"], x["hypothesis_id"]))
    ranked = ranked[:limit]
    return {"topic": topic, "count": len(ranked),
            "coverage_context": {"knowledge_nodes": nodes, "knowledge_edges": edges,
                                 "research_coverage": coverage, "knowledge_gap": knowledge_gap},
            "ranking_factors": ["novelty", "expected_information_gain", "uncertainty",
                                "historical_relevance", "implementation_cost", "portfolio_impact",
                                "validation_complexity", "research_coverage", "knowledge_gap"],
            "recommendations": ranked, "recommended_next": ranked[0] if ranked else {},
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Intelligent Experiment Prioritization(읽기전용) — 기존 7요인 + 3요인 확장. "
                     "추천만, 새 스코어러/원장 없음. 사람이 다음 실험을 결정.")}
