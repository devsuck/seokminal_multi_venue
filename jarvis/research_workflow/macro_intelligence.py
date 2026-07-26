"""Macro Intelligence Layer (P153) — 매크로 환경을 연구 컨텍스트에 연결한다. **읽기 전용, 예측 엔진 없음.**

**재사용**: FRED provider·ECOS provider(카탈로그)·regime detection·event_stream. 분석: interest rates·
inflation·employment·liquidity·economic cycle. 출력: MacroContextReport {macro_state, indicators,
historical_similarity, affected_assets, uncertainty}. **예측(forecasting) 없음** — 컨텍스트만. 새 저장소 없음.

원칙(문서 §Constitution, §P153): 통합·조율만. 결정적. 거래·집행·예측 없음.
"""
from __future__ import annotations

# 매크로 지표 키(FRED/ECOS 계열) → 카테고리
_INDICATORS = {
    "interest_rate": ("rate", "fed_funds", "base_rate", "policy_rate", "yield_10y"),
    "inflation": ("cpi", "inflation", "pce", "ppi"),
    "employment": ("unemployment", "nonfarm", "payroll", "jobless"),
    "liquidity": ("m2", "liquidity", "reserves", "credit_spread"),
}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _classify_indicator(cat: str, value) -> str:
    """지표 값 → 상태 라벨(결정적, 예측 아님)."""
    v = _num(value)
    if v is None:
        return "UNKNOWN"
    if cat == "interest_rate":
        return "HIGH" if v >= 4.0 else "LOW" if v <= 1.0 else "MODERATE"
    if cat == "inflation":
        return "HIGH" if v >= 4.0 else "LOW" if v <= 2.0 else "MODERATE"
    if cat == "employment":
        return "WEAK" if v >= 5.0 else "STRONG" if v <= 4.0 else "MODERATE"
    if cat == "liquidity":
        return "TIGHT" if v < 0 else "AMPLE"
    return "UNKNOWN"


def build_macro_context(*, indicators: dict | None = None, assistant=None) -> dict:
    """MacroContextReport(읽기전용) — 매크로 상태·지표·과거유사·영향자산·불확실성. 예측 없음."""
    ind = indicators or {}
    # 지표 분류
    classified = {}
    for cat, keys in _INDICATORS.items():
        val = next((ind[k] for k in ind if any(kw in str(k).lower() for kw in keys)), None)
        classified[cat] = {"value": val, "state": _classify_indicator(cat, val)}

    # 레짐 — regime 재사용
    regime = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"])
                   .detect_regime(ind, assistant=assistant), {"regime": "UNKNOWN"})

    # 경제 사이클 상태(결정적 조합)
    macro_state = _cycle(classified, regime)

    # 영향 자산(결정적) — 금리↑→성장주/채권 민감, 인플레↑→원자재 등
    affected = _affected_assets(classified)

    # 과거 유사 — recall
    historical = _safe(lambda: _recall(assistant, f"macro {macro_state}"), {})

    # 불확실성 — 미상 지표 비율
    unknowns = sum(1 for c in classified.values() if c["state"] == "UNKNOWN")
    uncertainty = "HIGH" if unknowns >= 3 else "MEDIUM" if unknowns >= 1 else "LOW"

    return {"macro_state": macro_state, "indicators": classified,
            "regime": regime.get("regime") if isinstance(regime, dict) else "UNKNOWN",
            "historical_similarity": historical, "affected_assets": affected,
            "uncertainty": uncertainty,
            "providers": ["FRED", "ECOS"],
            "report_type": "MacroContextReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("MacroContextReport(읽기전용) — 상태·지표·과거·영향자산·불확실성. 예측 아님. "
                     "FRED/ECOS/regime/event_stream 재사용, 새 저장소 없음.")}


def _cycle(classified, regime) -> str:
    r = classified["interest_rate"]["state"]
    infl = classified["inflation"]["state"]
    if r == "HIGH" and infl == "HIGH":
        return "TIGHTENING"
    if r == "LOW" and classified["employment"]["state"] == "WEAK":
        return "EASING/RECESSION_RISK"
    if r == "UNKNOWN" and infl == "UNKNOWN":
        return "UNKNOWN"
    return "MID_CYCLE"


def _affected_assets(classified) -> list:
    out = []
    if classified["interest_rate"]["state"] == "HIGH":
        out.append({"asset_class": "growth_equity/long_bonds", "sensitivity": "HIGH", "direction": "headwind"})
    if classified["inflation"]["state"] == "HIGH":
        out.append({"asset_class": "commodities/real_assets", "sensitivity": "MEDIUM", "direction": "tailwind"})
    if classified["liquidity"]["state"] == "TIGHT":
        out.append({"asset_class": "risk_assets", "sensitivity": "HIGH", "direction": "headwind"})
    return out or [{"asset_class": "broad", "sensitivity": "UNKNOWN", "direction": "지표 미연결"}]


def _recall(assistant, topic):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(topic)
    return {"topic": topic, "prior_records": r.total_hits, "tried_before": r.tried_before}
