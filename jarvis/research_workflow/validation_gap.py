"""Validation Gap Intelligence (P104) — 백테스트 vs 페이퍼 격차를 **다차원 진단**한다. **읽기 전용.**

차원: performance gap · risk gap · cost gap · regime gap · behavior gap. **재사용**: forward_testing.analyze
(P94)·StrategyRiskReasoner 실패 분류체계·research_assistant.recall·classify_failure(9-way taxonomy).
산출: Validation Intelligence Report(가능한 원인: 과적합·레짐 변화·비용 과소평가 등).

원칙(문서 §Constitution, §P104): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _metrics(d: dict) -> dict:
    d = d or {}
    return d.get("metrics") if isinstance(d.get("metrics"), dict) else d


def analyze_gap(backtest: dict, paper: dict, *, spec: dict | None = None, assistant=None) -> dict:
    """백테스트 vs 페이퍼 → Validation Intelligence Report(5차원 격차 + 가능한 원인). 결정적·읽기전용."""
    e, p = _metrics(backtest), _metrics(paper)
    name = str((backtest or {}).get("strategy_name", "") or "research")

    # forward_testing.analyze 재사용(차이·슬리피지·비용오류·레짐·누설)
    try:
        from jarvis.research_workflow.forward_testing import analyze as fwd_analyze
        fwd = fwd_analyze(backtest, paper, spec=spec)
    except Exception:  # noqa: BLE001
        fwd = {"difference": {}, "findings": []}
    diff = fwd.get("difference", {})

    # 1) performance gap
    perf = {"return_gap": diff.get("return_gap"), "sharpe_gap": diff.get("sharpe_gap"),
            "severity": diff.get("severity", "LOW")}
    # 2) risk gap — StrategyRiskReasoner(실패 분류체계) 재사용
    risk = {}
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
        rep = StrategyRiskReasoner().risk_report(name, p or e)
        risk = {"main_risk": rep.main_risk, "main_risk_label": rep.main_risk_label,
                "weakness": rep.weakness, "drawdown_gap": diff.get("drawdown_gap")}
    except Exception:  # noqa: BLE001
        risk = {"drawdown_gap": diff.get("drawdown_gap")}
    # 3) cost gap
    cost = {"slippage": fwd.get("slippage"), "cost_assumption_error": fwd.get("cost_assumption_error", False)}
    # 4) regime gap
    regime = {"regime_mismatch": fwd.get("regime_mismatch", False),
              "backtest_regime": (backtest or {}).get("regime"), "paper_regime": (paper or {}).get("regime")}
    # 5) behavior gap — 회전율/노출 변화(과적합/누설 행동 신호)
    turnover_gap = None
    et, pt = _num(e.get("turnover")), _num(p.get("turnover"))
    if et is not None and pt is not None:
        turnover_gap = round(pt - et, 4)
    behavior = {"turnover_gap": turnover_gap, "data_leakage_suspected": fwd.get("data_leakage_suspected", False)}

    # 가능한 원인 — 9-way failure taxonomy 로 분류
    causes = _possible_causes(perf, cost, regime, behavior, fwd.get("findings", []))
    # 과거 유사 — recall
    recall = {}
    try:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine()
        r = assistant.recall(name)
        recall = {"prior_records": r.total_hits, "tried_before": r.tried_before}
    except Exception:  # noqa: BLE001
        pass

    finding = ("Paper performance below expectation" if _num(perf["return_gap"]) is not None
               and _num(perf["return_gap"]) < 0 else "No material shortfall detected")
    return {"strategy": name, "finding": finding,
            "gaps": {"performance": perf, "risk": risk, "cost": cost, "regime": regime,
                     "behavior": behavior},
            "possible_causes": causes, "findings": fwd.get("findings", []),
            "historical_similarity": recall, "learning_feedback": fwd.get("learning_feedback", ""),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("검증 격차 인텔리전스(읽기전용) — forward_testing/risk taxonomy/recall 재사용. "
                     "학습은 기존 rmi_ 로. 거래·집행 없음.")}


def _possible_causes(perf, cost, regime, behavior, findings) -> list:
    """5차원 격차 → 9-way failure taxonomy 가능 원인(결정적)."""
    from jarvis.research_assistant.models import classify_failure
    causes = []
    if behavior.get("data_leakage_suspected"):
        causes.append({"cause": "DATA_LEAKAGE / OVERFITTING",
                       "why": "페이퍼 성과가 기대 대비 급감 — 인샘플 과적합/누설 신호"})
    if cost.get("cost_assumption_error"):
        causes.append({"cause": "COST_SENSITIVITY", "why": "실현 비용이 백테스트 가정 초과"})
    if regime.get("regime_mismatch"):
        causes.append({"cause": "REGIME_CHANGE", "why": "백테스트/페이퍼 레짐 불일치"})
    if _num(perf.get("return_gap")) is not None and _num(perf["return_gap"]) < 0 and not causes:
        causes.append({"cause": "OVERFITTING", "why": "성과 부족 — 강건성 재확인 필요"})
    # findings 텍스트도 분류
    for f in findings or []:
        cat = classify_failure(str(f))
        if cat != "UNCLASSIFIED" and not any(c["cause"].startswith(cat) for c in causes):
            causes.append({"cause": cat, "why": f})
    return causes or [{"cause": "UNCLASSIFIED", "why": "특이 격차 없음 — 표본/기간 확인"}]
