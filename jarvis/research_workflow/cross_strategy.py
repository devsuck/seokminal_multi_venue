"""Cross Strategy Intelligence (P83) — 전략들을 자동 비교한다. **읽기 전용, 새 엔진 없음.**

similarity·correlation·conflict·shared lessons·shared risks·portfolio overlap·decision differences 를
결정적으로 계산한다. **재사용**: PortfolioIntelligence(상관/중복), StrategyRiskReasoner(리스크),
research_assistant.recall(공유 교훈). 새 포트폴리오/리스크 엔진을 만들지 않는다.
"""
from __future__ import annotations


def _profile_type(name):
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import _profile
        return _profile(name)["type"]
    except Exception:  # noqa: BLE001
        return "generic"


def _recall_refs(assistant, name):
    try:
        r = assistant.recall(name)
        refs = set()
        for hits in (r.source_hits or {}).values():
            for h in hits:
                refs.add(str(h.get("text", ""))[:60])
        return refs
    except Exception:  # noqa: BLE001
        return set()


def _risk(name, metrics):
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
        return StrategyRiskReasoner().risk_report(name, metrics or {})
    except Exception:  # noqa: BLE001
        return None


def compare(a: dict, b: dict, *, assistant=None) -> dict:
    """전략 2개 비교(결정적). a/b: {name, returns?, max_drawdown?, metrics?, regimes?, holdings?}."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    na, nb = str(a.get("name", "A")), str(b.get("name", "B"))

    # 상관/중복/분산 — PortfolioIntelligence 재사용
    from jarvis.portfolio_research.intelligence import PortfolioIntelligence
    comb = PortfolioIntelligence().combination_analysis([a, b])
    pair = comb.pairs[0] if comb.pairs else {}
    correlation = pair.get("correlation")
    overlap = pair.get("overlap")

    # 유사도(유형 일치 + 교훈 겹침)
    ta, tb = _profile_type(na), _profile_type(nb)
    refs_a, refs_b = _recall_refs(assistant, na), _recall_refs(assistant, nb)
    shared_lessons = sorted(refs_a & refs_b)[:8]
    jaccard = round(len(refs_a & refs_b) / len(refs_a | refs_b), 4) if (refs_a | refs_b) else 0.0
    type_match = 1.0 if ta == tb else 0.0
    similarity = round(0.5 * type_match + 0.3 * jaccard
                       + 0.2 * (abs(correlation) if correlation is not None else 0.0), 4)

    # 공유 리스크
    ra, rb = _risk(na, a.get("metrics")), _risk(nb, b.get("metrics"))
    shared_risks = []
    if ra and rb:
        shared_risks = sorted(set(ra.category_flags) & set(rb.category_flags))
    conflict = bool(correlation is not None and correlation < -0.3)  # 반대 방향

    return {"a": na, "b": nb, "similarity": similarity, "correlation": correlation,
            "conflict": conflict, "shared_lessons": shared_lessons, "shared_risks": shared_risks,
            "portfolio_overlap": overlap, "diversification": pair.get("diversification"),
            "type_a": ta, "type_b": tb,
            "decision_differences": {"main_risk_a": ra.main_risk if ra else None,
                                     "main_risk_b": rb.main_risk if rb else None},
            "is_advisory": True, "is_decision": False,
            "note": "PortfolioIntelligence/RiskReasoner/recall 재사용 — 새 엔진 없음."}


def compare_all(strategies: list, *, assistant=None) -> dict:
    """전략 리스트 → 쌍별 비교 매트릭스(결정적)."""
    strats = [s for s in (strategies or []) if isinstance(s, dict)]
    pairs = []
    for i in range(len(strats)):
        for j in range(i + 1, len(strats)):
            pairs.append(compare(strats[i], strats[j], assistant=assistant))
    return {"strategies": [str(s.get("name", f"S{k}")) for k, s in enumerate(strats)],
            "pairs": pairs, "count": len(pairs), "is_advisory": True, "is_decision": False}
