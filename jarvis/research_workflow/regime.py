"""Market Regime Detection (P87) — 시장 환경 분석. **읽기 전용, 결정적. 거래·신호 없음.**

레짐 분류(Trend/Mean-Reversion/Risk-On/Risk-Off/Inflation/Deflation/Liquidity Expansion/Contraction/
Volatility Shock) + confidence + 과거 유사 기간 + 과거 성과/실패 전략. **재사용**: 기존 레짐 감지(있으면)·
research memory(recall)·strategy history. 시장 지표가 없으면 UNKNOWN(정직).

원칙(문서 §Constitution, §P87): 통합·조율만. 결정적. 거래·집행 없음 — 연구 추천일 뿐.
"""
from __future__ import annotations

# 과거 레짐 시그니처(정적 참조) — 유사 기간 매칭용
_HISTORICAL = [
    {"period": "2008", "labels": ["RISK_OFF", "LIQUIDITY_CONTRACTION", "VOLATILITY_SHOCK", "DEFLATION"]},
    {"period": "2020Q1", "labels": ["RISK_OFF", "VOLATILITY_SHOCK", "LIQUIDITY_CONTRACTION"]},
    {"period": "2021", "labels": ["RISK_ON", "LIQUIDITY_EXPANSION", "TREND"]},
    {"period": "2022", "labels": ["RISK_OFF", "INFLATION", "LIQUIDITY_CONTRACTION"]},
    {"period": "2017", "labels": ["RISK_ON", "TREND", "LOW_VOL"]},
]
# 레짐 → 유리/불리 전략 유형(결정적 매핑)
_FAVORABLE = {
    "RISK_OFF": ["defensive factors", "quality", "low-vol"], "INFLATION": ["commodities", "value", "carry"],
    "LIQUIDITY_CONTRACTION": ["defensive factors", "quality"], "VOLATILITY_SHOCK": ["vol/convexity", "tail hedges"],
    "RISK_ON": ["momentum", "high-beta"], "LIQUIDITY_EXPANSION": ["momentum", "growth"],
    "TREND": ["trend-following", "momentum"], "MEAN_REVERSION": ["mean-reversion", "stat-arb"],
    "DEFLATION": ["duration", "quality"],
}
_UNFAVORABLE = {
    "RISK_OFF": ["high-beta momentum", "small-cap"], "LIQUIDITY_CONTRACTION": ["high-beta momentum", "leverage"],
    "VOLATILITY_SHOCK": ["short-vol", "carry"], "INFLATION": ["long-duration", "growth"],
    "TREND": ["mean-reversion"], "MEAN_REVERSION": ["breakout/trend"],
}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify(indicators: dict) -> tuple:
    """지표 dict → (labels, confidence). 결정적. 지표 없으면 ([], 0.0)."""
    ind = indicators or {}
    labels: list = []
    trend = _num(ind.get("trend_strength"))
    vol = _num(ind.get("volatility"))
    liq = _num(ind.get("liquidity"))           # + 확장 / - 수축
    infl = _num(ind.get("inflation"))
    breadth = _num(ind.get("risk_appetite"))   # + risk-on / - risk-off
    if trend is not None:
        labels.append("TREND" if trend >= 0.5 else "MEAN_REVERSION")
    if vol is not None and vol >= 0.3:
        labels.append("VOLATILITY_SHOCK")
    if breadth is not None:
        labels.append("RISK_ON" if breadth >= 0 else "RISK_OFF")
    if liq is not None:
        labels.append("LIQUIDITY_EXPANSION" if liq >= 0 else "LIQUIDITY_CONTRACTION")
    if infl is not None:
        labels.append("INFLATION" if infl >= 0.03 else "DEFLATION" if infl <= -0.005 else None)
    labels = [x for x in labels if x]
    present = sum(1 for k in ("trend_strength", "volatility", "liquidity", "inflation",
                              "risk_appetite") if k in ind)
    confidence = round(min(1.0, present / 5.0), 4)
    return labels, confidence


def detect_regime(indicators: dict | None = None, *, assistant=None) -> dict:
    """현재 레짐 + confidence + 과거 유사 기간 + 유리/불리 전략(결정적, 읽기전용)."""
    labels, confidence = classify(indicators or {})
    if not labels:
        return {"regime": "UNKNOWN", "labels": [], "confidence": 0.0,
                "note": "시장 지표 미제공 — 정직하게 UNKNOWN. 지표(trend_strength/volatility/liquidity/"
                        "inflation/risk_appetite) 제공 시 분류.", "is_advisory": True, "is_decision": False}
    lset = set(labels)
    matches = sorted(_HISTORICAL, key=lambda h: -len(lset & set(h["labels"])))
    similar = [{"period": h["period"], "overlap": sorted(lset & set(h["labels"]))}
               for h in matches if lset & set(h["labels"])][:3]
    favorable = sorted({s for lb in labels for s in _FAVORABLE.get(lb, [])})
    unfavorable = sorted({s for lb in labels for s in _UNFAVORABLE.get(lb, [])})

    # research memory — 이 레짐에서 실패한 전략 회상(재사용)
    failed_here = []
    try:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine()
        for lb in labels:
            mc = assistant.mistake_check(lb.lower().replace("_", " "))
            if mc.get("made_this_mistake"):
                failed_here.append({"regime": lb, "past_failures": mc.get("failure_count")})
    except Exception:  # noqa: BLE001
        pass

    return {"regime": " + ".join(labels), "labels": labels, "confidence": confidence,
            "historical_similar_periods": similar,
            "favorable_strategies": favorable, "unfavorable_strategies": unfavorable,
            "historically_failed_here": failed_here,
            "recommended_research": favorable[:3], "avoid": unfavorable[:3],
            "is_advisory": True, "is_decision": False,
            "note": "레짐 분류·추천은 연구 자문일 뿐 — 사람이 결정. 거래·집행 없음."}
