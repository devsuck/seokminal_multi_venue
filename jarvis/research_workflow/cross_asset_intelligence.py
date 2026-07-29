"""Cross Asset Intelligence (P156) — 서로 다른 자산군을 연결한다. **읽기 전용, 포트폴리오 배분 없음.**

지원: Equity·ETF·Index·Commodity·FX·Macro. 분석: correlation·relationship changes·historical regimes·
risk transmission. **재사용**: supply_chain_impact 관계 그래프·regime·recall. 출력: CrossAssetReport.
**포트폴리오 배분 없음.** 새 저장소 없음.

원칙(문서 §Constitution, §P156): 통합·조율만. 결정적. 거래·집행·배분 없음.
"""
from __future__ import annotations

ASSET_CLASSES = ("Equity", "ETF", "Index", "Commodity", "FX", "Macro")

# 자산군 간 리스크 전이(정적 참조, 결정적) — 배분 아님, 관계 맵일 뿐
_TRANSMISSION = (
    ("Macro", "Equity", "rates/inflation → discount rate"),
    ("Macro", "FX", "policy divergence → currency"),
    ("Commodity", "Equity", "input cost → margins"),
    ("Index", "Equity", "beta / systematic"),
    ("FX", "Commodity", "USD ↔ commodity inverse"),
    ("ETF", "Equity", "flow → constituents"),
)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _corr_label(v):
    try:
        c = float(v)
    except (TypeError, ValueError):
        return "UNKNOWN"
    a = abs(c)
    sign = "+" if c >= 0 else "-"
    return f"{sign}{'HIGH' if a >= 0.6 else 'MODERATE' if a >= 0.3 else 'LOW'}"


def build_cross_asset(*, assets=None, correlations: dict | None = None, market: dict | None = None,
                      assistant=None) -> dict:
    """CrossAssetReport(읽기전용) — 자산군 관계·상관·레짐·리스크 전이. 배분 아님. 결정적.

    correlations: {"AAPL~SPY": 0.7, ...} 주면 라벨링. 없으면 관계 맵/레짐만(정직).
    """
    corr = correlations or {}
    corr_view = [{"pair": k, "value": v, "label": _corr_label(v)} for k, v in corr.items()]

    # 레짐 — regime(상관은 레짐 의존)
    regime = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"])
                   .detect_regime(market or {}, assistant=assistant), {"regime": "UNKNOWN"})

    # 리스크 전이 경로(정적 관계 맵)
    transmission = [{"from": a, "to": b, "channel": ch} for a, b, ch in _TRANSMISSION]

    # 관계 변화(결정적) — 고상관 페어는 레짐 전환 시 분산효과 감소 경고
    relationship_changes = []
    for cv in corr_view:
        if cv["label"].endswith("HIGH"):
            relationship_changes.append({"pair": cv["pair"],
                                         "note": "고상관 — 레짐 전환 시 동조화/분산효과 감소 위험"})

    # 과거 레짐 유사 — recall
    historical = _safe(lambda: _recall(assistant, f"cross-asset {regime.get('regime')}"), {})

    return {"asset_classes": list(ASSET_CLASSES),
            "correlations": corr_view,
            "relationship_changes": relationship_changes,
            "risk_transmission": transmission,
            "current_regime": regime.get("regime") if isinstance(regime, dict) else "UNKNOWN",
            "historical_regimes": historical,
            "report_type": "CrossAssetReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("CrossAssetReport(읽기전용) — 자산군 관계·상관·레짐·리스크 전이. 포트폴리오 배분 아님. "
                     "supply_chain/regime/recall 재사용, 새 저장소 없음.")}


def _recall(assistant, topic):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(topic)
    return {"topic": topic, "prior_records": r.total_hits, "tried_before": r.tried_before}
