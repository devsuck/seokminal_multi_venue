"""Sector Intelligence Engine (P152) — 시장 섹터·테마를 이해한다. **읽기 전용, 투자 랭킹 없음.**

**재사용**: knowledge_graph·company_monitor·market intelligence·supply_chain_impact(관계 그래프). 분석:
sector relationships·sector events·company concentration·historical sector behavior. 출력: SectorIntelligenceReport
{sector, key_entities, events, historical_context, risk_factors, research_questions}. 새 저장소 없음.

원칙(문서 §Constitution, §P152): 통합·조율만. 결정적. 거래·집행·랭킹 없음.
"""
from __future__ import annotations

# 섹터 → 대표 개체/ETF(정적 참조, supply_chain 그래프 보강용). 랭킹 아님.
_SECTOR_SEED = {
    "semiconductor": ["TSMC", "NVIDIA", "AMD", "ASML", "SMH", "SOXX"],
    "ai_infra": ["NVIDIA", "AI_Server", "Power_Infra", "TSMC"],
    "tech": ["Apple", "NVIDIA", "Foxconn"],
}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def analyze_sector(sector: str, *, events=None, assistant=None) -> dict:
    """섹터 → SectorIntelligenceReport(핵심개체·이벤트·과거·리스크·연구질문). 결정적·읽기전용."""
    name = (sector or "").strip()
    seed = _SECTOR_SEED.get(name.lower(), [])

    # 관계 그래프에서 섹터 관련 개체 — supply_chain_impact 재사용
    key_entities = list(seed)
    relationships = {}
    if seed:
        prop = _safe(lambda: __import__("jarvis.research_workflow.supply_chain_impact",
                                        fromlist=["propagate"]).propagate({"entity": seed[0],
                     "text": f"{name} sector"}), {})
        for a in prop.get("affected_entities", [])[:12]:
            if a["entity"] not in key_entities:
                key_entities.append(a["entity"])
        relationships = {"direct_suppliers": prop.get("direct_suppliers", []),
                         "customers": prop.get("customers", []),
                         "competitors": prop.get("competitors", []),
                         "related_sectors": prop.get("related_sectors", [])}

    # 섹터 이벤트 — event_stream(주어진 이벤트)
    ev = _safe(lambda: __import__("jarvis.research_workflow.event_stream", fromlist=["stream"])
               .stream(events or [], assistant=assistant), {"research_events": []})

    # 회사 집중도(결정적) — 상위 개체 수 대비 시드
    concentration = {"key_entity_count": len(key_entities),
                     "concentration": "HIGH" if len(seed) and len(seed) <= 4 else "MEDIUM"}

    # 과거 섹터 행동 — recall
    historical = _safe(lambda: _recall(assistant, name or (seed[0] if seed else "sector")), {})

    # 리스크 요인(결정적) — 관계/집중 기반
    risk_factors = []
    if concentration["concentration"] == "HIGH":
        risk_factors.append("소수 개체 집중 — 공급/수요 충격 전파 위험")
    if relationships.get("competitors"):
        risk_factors.append(f"경쟁 심화 가능: {', '.join(relationships['competitors'][:3])}")
    risk_factors = risk_factors or ["표준 섹터 리스크 — 레짐/수급 확인"]

    # 연구 질문(결정적)
    research_questions = [
        f"{name} 섹터의 리드-래그 전파는 어느 개체에서 시작되는가?",
        f"{name} 관련 과거 실패의 공통 원인은?",
        f"현재 레짐에서 {name} 섹터 강건성은?",
    ]
    return {"sector": name or "unknown", "key_entities": key_entities[:15],
            "relationships": relationships, "events": ev.get("research_events", [])[:8],
            "company_concentration": concentration, "historical_context": historical,
            "risk_factors": risk_factors, "research_questions": research_questions,
            "report_type": "SectorIntelligenceReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("SectorIntelligenceReport(읽기전용) — 관계·이벤트·집중·과거·리스크·질문. 투자 랭킹 아님. "
                     "knowledge_graph/supply_chain/company_monitor 재사용, 새 저장소 없음.")}


def _recall(assistant, topic):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(topic)
    return {"topic": topic, "prior_records": r.total_hits, "tried_before": r.tried_before}


def supported_sectors() -> list:
    return list(_SECTOR_SEED)
