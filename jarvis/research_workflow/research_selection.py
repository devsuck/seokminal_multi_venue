"""Research Selection Intelligence (P188) — 검증 완료 연구를 평가한다. **연구 품질 평가, 투자 추천 아님.**

평가 기준(결정적): statistical_robustness·cost_sensitivity·regime_stability·reproducibility·
historical_similarity·failure_risk. 출력: Strong Evidence · Medium Evidence · Weak Evidence · Rejected.

**투자 추천이 아니다 — 연구 품질 평가다.**
**재사용**: quality_monitor(P106)·validation_intelligence(P187)·semantic_recall(P133).
원칙(문서 §Constitution, §P188): 통합·조율만 · 결정적 · 자문 전용 · 투자 추천 아님 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

EVIDENCE_GRADES = ("STRONG", "MEDIUM", "WEAK", "REJECTED")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _num(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _count(v) -> int:
    if isinstance(v, list):
        return len(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _criteria(backtest, validation):
    """6개 연구 품질 기준(0~1, 결정적)."""
    m = (backtest or {}).get("metrics") or backtest or {}
    sharpe = _num(m.get("sharpe"), 0.0)
    p = _num(m.get("empirical_p"))
    oos = _num(m.get("out_of_sample"))
    wf = _num(m.get("walk_forward"))
    cls = str((validation or {}).get("classification", "")).upper()

    statistical = round(min(1.0, max(0.0, (sharpe or 0) / 1.0)), 4)
    if p is not None:
        statistical = round(0.5 * statistical + 0.5 * (1.0 - min(1.0, p)), 4)
    cost_sensitivity = 0.6 if m.get("return") is not None else 0.4
    regime_stability = 0.5
    if oos is not None and wf is not None:
        regime_stability = round(1.0 if (oos > 0 and wf > 0) else (0.3 if oos <= 0 else 0.6), 4)
    reproducibility = 0.8 if cls == "ROBUST" else (0.2 if cls == "FAILED" else 0.5)
    # 과거 유사 성공 존재 → 유사성 높음
    hist = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                    fromlist=["recall_context"]).recall_context(
                                        str((backtest or {}).get("strategy_name", ""))), {}) or {}
    historical_similarity = round(min(1.0, _count(hist.get("past_conclusions")) / 4.0), 4)
    failure_risk = round(1.0 - reproducibility, 4)
    return {"statistical_robustness": statistical, "cost_sensitivity": cost_sensitivity,
            "regime_stability": regime_stability, "reproducibility": reproducibility,
            "historical_similarity": historical_similarity, "failure_risk": failure_risk}


def _grade(c, classification):
    if classification == "FAILED":
        return "REJECTED"
    score = round(0.3 * c["statistical_robustness"] + 0.2 * c["regime_stability"]
                  + 0.25 * c["reproducibility"] + 0.15 * c["cost_sensitivity"]
                  - 0.25 * c["failure_risk"] + 0.1 * c["historical_similarity"], 4)
    if score >= 0.55:
        return "STRONG"
    if score >= 0.35:
        return "MEDIUM"
    if score >= 0.15:
        return "WEAK"
    return "REJECTED"


def evaluate_research(backtest: dict, *, validation: dict | None = None) -> dict:
    """검증 완료 연구 → 증거 품질 등급(Strong/Medium/Weak/Rejected). 연구 품질 평가, 투자 추천 아님. 결정적."""
    if validation is None:
        validation = _safe(lambda: __import__("jarvis.research_workflow.validation_intelligence",
                                              fromlist=["build_validation_report"]
                                              ).build_validation_report(backtest or {}), {}) or {}
    classification = str(validation.get("classification", "")).upper()
    criteria = _criteria(backtest, validation)
    grade = _grade(criteria, classification)
    return {"evidence_grade": grade, "validation_classification": classification,
            "criteria": criteria,
            "strategy": (backtest or {}).get("strategy_name") or (backtest or {}).get("strategy_id"),
            "is_investment_recommendation": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Selection Intelligence(읽기전용) — 6기준 연구 품질 평가 → 증거 등급. "
                     "투자 추천 아님. 새 엔진 없음. 사람이 결정.")}
