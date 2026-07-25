"""News Research Pipeline (P114) — 뉴스 소스를 연구 컨텍스트로 연결한다. **읽기 전용, 신호 아님.**

Pipeline: News API → News Intelligence → Event Classification → Research Context.
추출: company·sector·event type·importance·historical similarity. **재사용**: providers.NewsProvider +
news_intelligence.stream(P97). **sentiment trading score 없음** — 연구 컨텍스트일 뿐.

원칙(문서 §Constitution, §P114): 통합·조율만. 결정적. 거래·집행·신호 없음.
"""
from __future__ import annotations


def run(headlines, *, source: str = "news", assistant=None) -> dict:
    """뉴스 헤드라인 배치 → 연구 이벤트(company·sector·type·importance·historical) + 검토 큐.

    news_intelligence.stream 재사용. importance = relevance_score(트레이딩 점수 아님).
    """
    from jarvis.research_workflow.news_intelligence import stream
    items = []
    for h in (headlines or []):
        if isinstance(h, dict):
            items.append({"text": h.get("text") or h.get("headline") or "",
                          "entity": h.get("entity", "")})
        else:
            items.append({"text": str(h), "entity": ""})
    res = stream(items, assistant=assistant)
    # 연구 컨텍스트 정규화(추출 필드 명시) — 재분석 없이 stream 결과에서 파생
    context = [{"headline": e["headline"], "company": e["affected_companies"][:5],
                "sector": e["affected_sectors"][:5], "event_type": e["event_type"],
                "importance": e["relevance_score"], "historical_similarity": e["historical_similarity"]}
               for e in res.get("events", [])]
    res["research_context"] = context
    res["source"] = source
    res["pipeline"] = "news"
    res["extracts"] = ["company", "sector", "event_type", "importance", "historical_similarity"]
    res["note"] = ("뉴스 연구 파이프라인(읽기전용) — News→Intelligence→Classification→Research Context. "
                   "sentiment trading score 없음, 신호 아님.")
    return res
