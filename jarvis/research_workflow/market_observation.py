"""Market Observation Intelligence (P182) — 시장 변화에서 **연구 기회**를 자동 발견한다. **관찰만, 신호 아님.**

입력(모두 기존 모듈/주입 재사용): regime(P89)·macro_intelligence(P152)·sector_intelligence(P153)·
opportunity_discovery(P92)·event_stream(P97). 출력: Research Opportunity Object —
{type, observation, affected_assets, possible_questions, confidence, requires_validation}.

**Opportunity 는 Signal 이 아니다.** possible_questions 는 연구 질문일 뿐 매매 지시가 아니다.
금지: BUY·SELL·LONG·SHORT·ALLOCATE.

원칙(문서 §Constitution, §P182): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

# 기회 유형(연구 관점) — 매매 방향 아님
OPP_TYPES = ("REGIME_CHANGE", "VOLATILITY_EXPANSION", "CORRELATION_SHIFT", "EARNINGS_EVENT",
             "NEWS_CATALYST", "INSIDER_ACTIVITY", "MACRO_SHIFT", "SECTOR_ROTATION")
# 절대 산출하지 않는 매매 지시어(방어적 필터)
_FORBIDDEN = ("BUY", "SELL", "LONG", "SHORT", "ALLOCATE")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _oid(*parts):
    import hashlib
    return "OPP:" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _opportunity(otype, observation, questions, *, assets=None, confidence=0.5):
    # 방어: 질문에 매매 지시어가 들어가지 않도록(연구 질문만)
    qs = [q for q in (questions or []) if not any(w in str(q).upper().split() for w in _FORBIDDEN)]
    return {"opportunity_id": _oid(otype, observation), "type": otype,
            "observation": observation, "affected_assets": list(assets or []),
            "possible_questions": qs, "confidence": round(float(confidence), 4),
            "requires_validation": True, "is_signal": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False}


def _from_regime(signals):
    r = _safe(lambda: __import__("jarvis.research_workflow.regime",
                                 fromlist=["detect_regime"]).detect_regime(signals.get("indicators")
                                                                           if signals else None), {}) or {}
    label = str(r.get("regime") or r.get("label") or "")
    if not label or label == "UNKNOWN":
        return []
    return [_opportunity("REGIME_CHANGE", f"현 레짐: {label}",
                         ["Does momentum survive this regime?",
                          "Does volatility compression follow this regime?",
                          "Which factors are regime-conditional here?"],
                         confidence=float(r.get("confidence") or 0.55))]


def _from_macro(signals):
    m = _safe(lambda: __import__("jarvis.research_workflow.macro_intelligence",
                                 fromlist=["build_macro_context"]).build_macro_context(
                                     indicators=signals.get("macro") if signals else None), {}) or {}
    stance = str(m.get("stance") or m.get("regime") or "")
    if not stance:
        return []
    return [_opportunity("MACRO_SHIFT", f"매크로 스탠스: {stance}",
                         ["Does this macro stance change factor efficacy?",
                          "Is cross-asset correlation shifting under this macro?"],
                         confidence=0.5)]


def _from_sector(signals):
    secs = _safe(lambda: __import__("jarvis.research_workflow.sector_intelligence",
                                    fromlist=["supported_sectors"]).supported_sectors(), []) or []
    out = []
    for sec in [str(s) for s in secs][:2]:
        out.append(_opportunity("SECTOR_ROTATION", f"{sec} 섹터 관찰",
                                [f"Does {sec} relative strength persist?",
                                 f"Is {sec} volatility expanding (regime signal)?"],
                                assets=[], confidence=0.45))
    return out


def _from_signals(signals):
    """주입된 관찰(volatility/correlation/earnings/news/insider) → 기회. 라이브 소스 연동 지점."""
    out = []
    s = signals or {}
    if s.get("volatility_change"):
        out.append(_opportunity("VOLATILITY_EXPANSION",
                                f"변동성 변화: {s['volatility_change']}",
                                ["Does volatility compression follow this expansion?",
                                 "Do mean-reversion edges strengthen here?"],
                                assets=s.get("assets"), confidence=0.6))
    if s.get("correlation_change"):
        out.append(_opportunity("CORRELATION_SHIFT",
                                f"상관 변화: {s['correlation_change']}",
                                ["Is diversification benefit changing?",
                                 "Are pairs relationships breaking down?"],
                                assets=s.get("assets"), confidence=0.55))
    for ev in (s.get("earnings") or []):
        out.append(_opportunity("EARNINGS_EVENT", f"실적 이벤트: {ev}",
                                ["Does post-earnings drift exist here?"], confidence=0.5))
    for nw in (s.get("news") or []):
        out.append(_opportunity("NEWS_CATALYST", f"뉴스: {nw}",
                                ["Is this catalyst already priced?"], confidence=0.4))
    for ins in (s.get("insider") or []):
        out.append(_opportunity("INSIDER_ACTIVITY", f"내부자 활동: {ins}",
                                ["Does insider buying predict drift here?"], confidence=0.5))
    return out


def observe_market(*, signals: dict | None = None, limit: int = 20) -> dict:
    """시장 관찰 → Research Opportunity Objects(결정적·읽기전용). Opportunity 는 Signal 아님.

    signals(선택): {indicators, macro, volatility_change, correlation_change, earnings[], news[],
    insider[], assets[]} — 라이브 소스 연동 지점. 없으면 regime/macro/sector 로부터 유도.
    """
    opps = []
    opps += _from_signals(signals)
    opps += _from_regime(signals)
    opps += _from_macro(signals)
    opps += _from_sector(signals)

    # 중복 제거 + 정렬(confidence 내림차순, 결정적 타이브레이크)
    seen, uniq = set(), []
    for o in opps:
        if o["opportunity_id"] in seen:
            continue
        seen.add(o["opportunity_id"])
        uniq.append(o)
    uniq.sort(key=lambda x: (-x["confidence"], x["opportunity_id"]))
    uniq = uniq[:limit]

    by_type: dict = {}
    for o in uniq:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1

    return {"opportunity_count": len(uniq), "by_type": dict(sorted(by_type.items())),
            "opportunities": uniq,
            "sources": ["regime", "macro_intelligence", "sector_intelligence", "injected_signals"],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Market Observation Intelligence(읽기전용) — 시장 변화 → 연구 기회(Signal 아님). "
                     "possible_questions 는 연구 질문일 뿐. BUY/SELL/LONG/SHORT/ALLOCATE 없음. 사람이 결정.")}
