"""Opportunity Discovery Engine (P88) — 비정상 상황에서 **연구 아이디어**를 발견한다. **거래 신호 아님.**

유형: insider anomaly·supply disruption·price/fundamental divergence·macro shock·sector rotation·
sentiment extreme·liquidity imbalance. 각 기회는 title·reason·evidence·historical similarity·
related research·suggested hypothesis·confidence 를 포함. **재사용**: hypothesis_generator(가설),
recall(과거 유사), event_intelligence. **연구 아이디어만 생성 — 절대 트레이드 신호 아님.**

원칙(문서 §Constitution, §P88): 통합·조율만. 결정적. 거래·집행·자본배분 없음.
"""
from __future__ import annotations

# 이상 신호 유형 → 기회 템플릿(결정적)
_TYPES = {
    "insider_anomaly": ("Insider buying anomaly", "비정상 내부자 매수 클러스터 — 정보 우위 가설 후보"),
    "supply_disruption": ("Supply chain disruption", "공급망 충격 — 하류 개체 리드-래그 영향 가설"),
    "price_fundamental_divergence": ("Price/fundamental divergence", "가격-펀더멘털 괴리 — 평균회귀/재평가 가설"),
    "macro_shock": ("Macro shock", "매크로 충격 — 레짐 조건부 팩터 재평가"),
    "sector_rotation": ("Sector rotation", "섹터 로테이션 — 상대강도 전이 가설"),
    "sentiment_extreme": ("Sentiment extreme", "심리 극단 — 컨트라리언/평균회귀 가설"),
    "liquidity_imbalance": ("Liquidity imbalance", "유동성 불균형 — 체결충격/스프레드 가설"),
}


def _confidence(evidence) -> str:
    n = len(evidence or [])
    return "HIGH" if n >= 3 else "MEDIUM" if n >= 1 else "LOW"


def discover(signals: dict | None = None, *, assistant=None) -> dict:
    """이상 신호 → 기회 객체 리스트(결정적, 읽기전용). signals: {type: {entity, evidence:[...]}}."""
    sig = signals or {}
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    from jarvis.research_assistant.models import extract_topic

    opportunities = []
    for typ, payload in sig.items():
        if typ not in _TYPES:
            continue
        p = payload if isinstance(payload, dict) else {"entity": str(payload)}
        title, reason = _TYPES[typ]
        entity = str(p.get("entity", "")).strip()
        evidence = list(p.get("evidence", []))
        # 과거 유사 — recall 재사용
        topic = entity or extract_topic(title) or title
        recall = {}
        try:
            r = assistant.recall(topic)
            recall = {"tried_before": r.tried_before, "hits": r.total_hits}
        except Exception:  # noqa: BLE001
            pass
        suggested = f"{entity or title} — {reason.split('—')[-1].strip()}"
        opportunities.append({
            "type": typ, "title": f"{title}{f' · {entity}' if entity else ''}",
            "reason": reason, "evidence": evidence,
            "historical_similarity": recall,
            "related_research": f"recall({topic}) hits={recall.get('hits', 0)}",
            "suggested_hypothesis": suggested, "confidence": _confidence(evidence),
            "requires_human_review": True, "is_research_idea": True, "is_trade_signal": False})

    by_type: dict = {}
    for o in opportunities:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
    return {"opportunities": opportunities, "count": len(opportunities), "by_type": by_type,
            "is_advisory": True, "is_decision": False,
            "note": "연구 아이디어만 — 트레이드 신호가 아니다. 사람 검토·결정 필요."}
