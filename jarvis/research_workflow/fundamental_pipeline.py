"""Fundamental Intelligence (P115) — 재무제표·실적·밸류에이션을 연구 후보로 연결한다. **읽기 전용.**

Flow: Financial Data → Earnings Intelligence → Research Candidate.
지원: Revenue·EPS·Margin·Cashflow·Debt·Growth. **재사용**: providers.FundamentalProvider +
earnings_intelligence.analyze_earnings(P100). 새 저장소/엔진 없음.

원칙(문서 §Constitution, §P115): 통합·조율만. 결정적. 거래·집행·신호 없음.
"""
from __future__ import annotations

_FUND_METRICS = ("revenue", "eps", "margin", "cashflow", "debt", "growth")


def _to_earnings(fin: dict) -> dict:
    """재무/밸류에이션 raw → earnings_intelligence 입력(expected vs actual). 값 왜곡 없음."""
    f = fin or {}
    if "expected" in f or "actual" in f:
        return f
    expected = f.get("estimates") or f.get("consensus") or {}
    actual = {k: f[k] for k in _FUND_METRICS if k in f}
    return {"company": f.get("company") or f.get("entity") or f.get("symbol", ""),
            "period": f.get("period", ""), "expected": expected, "actual": actual}


def run(financials, *, source: str = "fundamental", assistant=None) -> dict:
    """재무/실적 배치 → 연구 후보(company·서프라이즈·전략영향 + 재무 지표). analyze_earnings 재사용."""
    from jarvis.research_workflow.earnings_intelligence import analyze_earnings
    candidates = []
    by_surprise: dict = {}
    for fin in (financials or []):
        e = analyze_earnings(_to_earnings(fin), assistant=assistant)
        by_surprise[e["overall_surprise"]] = by_surprise.get(e["overall_surprise"], 0) + 1
        candidates.append({"company": e["company"], "period": e["period"],
                           "overall_surprise": e["overall_surprise"],
                           "surprise": e["surprise"], "related_strategy_impact": e["related_strategy_impact"],
                           "historical_comparison": e["historical_comparison"],
                           "is_research_candidate": True, "is_trade_signal": e["is_trade_signal"]})
    return {"research_candidates": candidates, "count": len(candidates), "by_surprise": by_surprise,
            "source": source, "pipeline": "fundamental", "supported_metrics": list(_FUND_METRICS),
            "review_queue": [{"company": c["company"], "period": c["period"],
                              "surprise": c["overall_surprise"]} for c in candidates],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("펀더멘털 파이프라인(읽기전용) — Financial→Earnings Intelligence→Research Candidate. "
                     "새 저장소 없음, 신호 아님.")}
