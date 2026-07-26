"""Morning Market Briefing (P142) — 일일 시장 브리프를 생성한다. **읽기 전용, 신호 아님.**

Uses: market_intelligence(market_cockpit)·regime·event_stream·knowledge_brain(semantic_recall/knowledge_health).
구조: 1.Market Condition 2.Current Regime 3.Major Events 4.Research Opportunities 5.Risk Factors
6.Previous Lessons. **반드시 confidence·evidence·limitations 포함.** 새 저장소 없음.

원칙(문서 §Constitution, §P142): 통합·조율만. 결정적. 거래·집행·신호 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


class MorningBriefingGenerator:
    """모닝 브리핑 — 시장상황·레짐·이벤트·기회·리스크·과거교훈. RESEARCH_ONLY. 신호 아님."""

    def generate(self, *, market: dict | None = None, events=None, assistant=None) -> dict:
        """일일 Daily Market Brief(6섹션 + confidence·evidence·limitations). 결정적·읽기전용."""
        # 1) 시장 상황 — market_cockpit
        cockpit = _safe(lambda: __import__("jarvis.research_workflow.market_cockpit",
                                           fromlist=["build_market_cockpit"])
                        .build_market_cockpit(market or {}, {}), {})
        # 2) 현재 레짐 — regime
        regime = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"])
                       .detect_regime(market or {}, assistant=assistant), {"regime": "UNKNOWN"})
        # 3) 주요 이벤트 — event_stream
        ev = _safe(lambda: __import__("jarvis.research_workflow.event_stream", fromlist=["stream"])
                   .stream(events or [], assistant=assistant), {"research_events": [], "by_type": {}})
        # 4) 연구 기회 — opportunity_discovery
        opps = _safe(lambda: __import__("jarvis.research_workflow.opportunity_discovery",
                                        fromlist=["discover"]).discover({}, assistant=assistant),
                     {"opportunities": []})
        # 5) 리스크 요인 — regime avoid + knowledge health
        health = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                          fromlist=["build_knowledge_health"]).build_knowledge_health(), {})
        # 6) 과거 교훈 — semantic_recall(레짐/시장 주제)
        topic = regime.get("regime", "market") if isinstance(regime, dict) else "market"
        lessons = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                           fromlist=["recall_context"]).recall_context(f"market {topic}",
                        assistant=assistant), {})

        regime_labels = regime.get("labels", []) if isinstance(regime, dict) else []
        evidence = {"events_seen": ev.get("count", len(ev.get("research_events", []))),
                    "opportunities": len(opps.get("opportunities", [])),
                    "prior_research": lessons.get("prior_research_count", 0)}
        confidence = ("MEDIUM" if (regime.get("regime") not in (None, "UNKNOWN") and evidence["prior_research"])
                      else "LOW")
        return {"brief": {
                    "1_market_condition": cockpit.get("market_state", {}) if isinstance(cockpit, dict) else {},
                    "2_current_regime": {"regime": regime.get("regime"), "labels": regime_labels,
                                         "recommended_research": regime.get("recommended_research", [])},
                    "3_major_events": ev.get("research_events", [])[:8],
                    "4_research_opportunities": opps.get("opportunities", [])[:5],
                    "5_risk_factors": (regime.get("avoid", []) if isinstance(regime, dict) else []) +
                    ([f"knowledge health {health.get('grade')}"] if health.get("grade") in ("DEGRADED", "FAIR") else []),
                    "6_previous_lessons": {"similar_failures": lessons.get("similar_failures", []),
                                           "past_conclusions": lessons.get("past_conclusions", [])},
                },
                "confidence": confidence, "evidence": evidence,
                "limitations": ["브리프는 자문이며 투자 결정이 아니다 — 사람 검토 필수.",
                                "시장 지표 미연결 시 레짐 UNKNOWN(정직).",
                                "과거 교훈은 축적된 연구에 한함."],
                "brief_type": "Daily Market Brief",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "is_trade_signal": False,
                "note": ("Daily Market Brief(읽기전용) — 시장·레짐·이벤트·기회·리스크·교훈. 신호 아님. "
                         "market_intelligence/regime/event_stream/knowledge_brain 재사용, 새 저장소 없음.")}


def generate(*, market=None, events=None, assistant=None) -> dict:
    """모듈 진입점 — MorningBriefingGenerator.generate 래퍼."""
    return MorningBriefingGenerator().generate(market=market, events=events, assistant=assistant)
