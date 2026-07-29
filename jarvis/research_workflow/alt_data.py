"""Alternative Data Intelligence (P89) — 대체 연구 데이터 **프레임워크**. **연구 근거일 뿐, 투자 신호 아님.**

외부 공급자 없이 아키텍처를 구축한다. 지원: shipping·satellite·web traffic·hiring·app rankings·
social sentiment·search trends. 흐름: Alternative Data → Company/Sector → Knowledge Graph → Research
Memory. **재사용**: knowledge graph(개체 연결), rmi_(근거 저장). 새 저장소를 만들지 않는다.

원칙(문서 §Constitution, §P89): 통합·조율만. 결정적. 거래·집행 없음 — 연구 근거.
"""
from __future__ import annotations

# 지원 대체데이터 소스 + 매핑 대상(결정적 카탈로그)
ALT_SOURCES = {
    "shipping": {"maps_to": "sector", "signal": "trade volume / port congestion"},
    "satellite": {"maps_to": "company", "signal": "facility activity / parking counts"},
    "web_traffic": {"maps_to": "company", "signal": "site visits / engagement"},
    "hiring": {"maps_to": "company", "signal": "job postings / headcount trend"},
    "app_rankings": {"maps_to": "company", "signal": "app store rank / DAU proxy"},
    "social_sentiment": {"maps_to": "company", "signal": "social buzz / tone"},
    "search_trends": {"maps_to": "sector", "signal": "search interest index"},
}


def catalog() -> dict:
    """지원 대체데이터 소스 카탈로그(아키텍처) — 외부 공급자 불필요."""
    return {"sources": ALT_SOURCES, "count": len(ALT_SOURCES),
            "flow": ["Alternative Data", "Company/Sector", "Knowledge Graph", "Research Memory"],
            "is_advisory": True, "is_decision": False,
            "note": "대체데이터 프레임워크(아키텍처) — 연구 근거 전용, 투자 신호 아님."}


def observe(source: str, entity: str, value=None, *, direction: str = "", note: str = "",
            assistant=None, now: str = "", commit: bool = False) -> dict:
    """대체데이터 관측 1건 → 개체/섹터 연결 + (commit 시)기존 rmi_ 근거 저장. 신호 아님."""
    src = ALT_SOURCES.get(source)
    if not src:
        return {"error": f"unknown alt-data source {source}", "supported": list(ALT_SOURCES)}
    maps_to = src["maps_to"]
    evidence = {"source": source, "entity": entity, "maps_to": maps_to, "value": value,
                "direction": direction, "signal_meaning": src["signal"], "note": note}
    # 지식 그래프 연결(개체 노드) — 회상용 컨텍스트
    recall = {}
    try:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine()
        r = assistant.recall(entity)
        recall = {"tried_before": r.tried_before, "hits": r.total_hits}
    except Exception:  # noqa: BLE001
        pass
    # 근거를 기존 메모리에 교훈으로 저장(commit) — 새 저장소 없음
    stored = False
    if commit:
        try:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            les = (f"ALT-DATA [{source}] {entity} ({maps_to}) — {src['signal']} "
                   f"{direction} {value} {note}")
            ResearchMemoryIntelligenceEngine().record_lesson(
                origin=f"altdata:{source}:{entity}", lesson=les, evidence=evidence,
                impact="alt_data", now=now, commit=True)
            stored = True
        except Exception:  # noqa: BLE001
            pass
    return {"evidence": evidence, "maps_to": maps_to, "entity_recall": recall,
            "stored_as_research_evidence": stored,
            "is_research_evidence": True, "is_trade_signal": False,
            "is_advisory": True, "is_decision": False}
