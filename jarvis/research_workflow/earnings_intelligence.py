"""Earnings Intelligence (P100) — 실적을 **연구 인텔리전스**로. **읽기 전용, 신호 아님.**

Input: earnings releases·guidance·estimates·actuals. Expectation vs Reality → Earnings Event
(company·period·expected·actual·surprise·historical comparison·related strategy impact). **재사용**:
research memory(recall)·event system·opportunity_discovery. 양의 서프라이즈 → 과거 유사 실적 검색 → 연구 업데이트.

원칙(문서 §Constitution, §P100): 통합·조율만. 결정적. 거래·집행·신호 없음.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _surprise_label(expected, actual) -> tuple:
    """(surprise_pct, label) — 결정적."""
    e, a = _num(expected), _num(actual)
    if e is None or a is None or e == 0:
        return None, "UNKNOWN"
    pct = round((a - e) / abs(e), 4)
    label = "POSITIVE_SURPRISE" if pct >= 0.05 else "NEGATIVE_SURPRISE" if pct <= -0.05 else "IN_LINE"
    return pct, label


def analyze_earnings(earnings: dict, *, assistant=None) -> dict:
    """실적 1건 → Earnings Event(기대 vs 실제·서프라이즈·과거비교·전략영향). 결정적·읽기전용."""
    e = earnings or {}
    company = str(e.get("company") or e.get("entity") or e.get("symbol") or "").strip()
    period = str(e.get("period", ""))
    expected = e.get("expected") or {}
    actual = e.get("actual") or {}

    surprises = {}
    labels = []
    for metric in set(expected) | set(actual):
        pct, label = _surprise_label(expected.get(metric), actual.get(metric))
        surprises[metric] = {"expected": expected.get(metric), "actual": actual.get(metric),
                             "surprise_pct": pct, "label": label}
        if label in ("POSITIVE_SURPRISE", "NEGATIVE_SURPRISE"):
            labels.append(label)
    overall = ("POSITIVE_SURPRISE" if labels.count("POSITIVE_SURPRISE") > labels.count("NEGATIVE_SURPRISE")
               else "NEGATIVE_SURPRISE" if labels.count("NEGATIVE_SURPRISE") > 0 else "IN_LINE")

    # 과거 유사 실적 — recall 재사용
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    hist = {}
    try:
        r = assistant.recall(company)
        hist = {"prior_records": r.total_hits, "tried_before": r.tried_before}
    except Exception:  # noqa: BLE001
        pass

    # 관련 전략 영향(결정적) — PEAD/모멘텀은 서프라이즈에 민감
    strategy_impact = []
    if overall == "POSITIVE_SURPRISE":
        strategy_impact = ["post-earnings drift (PEAD)", "earnings momentum", "quality/growth"]
    elif overall == "NEGATIVE_SURPRISE":
        strategy_impact = ["short-side PEAD", "value trap check", "estimate-revision"]

    return {"company": company or "unknown", "period": period, "expected_metrics": expected,
            "actual_metrics": actual, "surprise": surprises, "overall_surprise": overall,
            "historical_comparison": hist, "related_strategy_impact": strategy_impact,
            "related_research": f"recall({company}) hits={hist.get('prior_records', 0)}",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "is_trade_signal": False}


def stream(earnings_list, *, assistant=None) -> dict:
    """실적 배치 → Earnings Event 스트림 + 검토 큐(읽기전용)."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    items = [analyze_earnings(x, assistant=assistant) for x in (earnings_list or [])]
    by_surprise: dict = {}
    for it in items:
        by_surprise[it["overall_surprise"]] = by_surprise.get(it["overall_surprise"], 0) + 1
    return {"events": items, "count": len(items), "by_surprise": by_surprise,
            "review_queue": [{"company": i["company"], "period": i["period"],
                              "surprise": i["overall_surprise"]} for i in items],
            "is_advisory": True, "is_decision": False,
            "note": "실적 → 연구 컨텍스트(읽기전용) — research memory/event/opportunity 재사용. 신호 아님."}
