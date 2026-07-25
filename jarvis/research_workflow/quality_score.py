"""Research Quality Score (P84) — 모든 연구 프로젝트를 결정적으로 채점한다. **읽기 전용, 새 저장소 없음.**

차원: reproducibility·walk-forward·random baseline·out-of-sample·transaction cost·liquidity·
failure learning·portfolio impact·paper performance·evidence·documentation·confidence·overall.
**재사용**: research_ingestion.validate_backtest, research_assistant.recall, ResearchCritic 임계.
결정적 스코어링만.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clip(x):
    return round(max(0.0, min(1.0, x)), 4)


def score_research(backtest: dict, *, assistant=None) -> dict:
    """백테스트/연구 dict → 품질 점수(0..1 차원 + overall 0..100). 결정적."""
    bt = backtest or {}
    m = bt.get("metrics") or {}
    name = str(bt.get("strategy_name", "") or "research")

    from jarvis.research_ingestion.models import validate_backtest
    v = validate_backtest(bt)

    wf = _num(m.get("walk_forward"))
    oos = _num(m.get("out_of_sample"))
    cost = _num(m.get("cost_impact"))
    rb = _num(m.get("random_baseline"))
    turnover = _num(m.get("turnover"))

    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    try:
        hits = int(assistant.recall(name).total_hits)
    except Exception:  # noqa: BLE001
        hits = 0
    try:
        mc = assistant.mistake_check(name)
        failure_learning = 1.0 if mc.get("made_this_mistake") else 0.3
    except Exception:  # noqa: BLE001
        failure_learning = 0.3

    dims = {
        "reproducibility": 1.0 if bt.get("source") else 0.6,
        "walk_forward": _clip(wf) if wf is not None else 0.0,
        "random_baseline": 1.0 if rb is not None else 0.0,
        "out_of_sample": _clip(oos) if oos is not None else 0.0,
        "transaction_cost": _clip(1 - (cost / 0.3)) if cost is not None else 0.0,
        "liquidity": _clip(1 - turnover) if turnover is not None else 0.6,
        "failure_learning": failure_learning,
        "portfolio_impact": 1.0 if bt.get("universe") else 0.4,
        "paper_performance": 0.5,   # 페이퍼 결과 있으면 별도 상향(중립 기본)
        "evidence": _clip(hits / 5.0),
        "documentation": 1.0 if (bt.get("hypothesis") and bt.get("entry_rules")) else 0.5,
        "confidence": 1.0 if v["validation_complete"] else 0.4,
    }
    # 페이퍼 성과(있으면)
    paper = bt.get("paper")
    if isinstance(paper, dict):
        pr, er = _num((paper.get("metrics") or paper).get("return")), _num(m.get("return"))
        if pr is not None and er not in (None, 0):
            dims["paper_performance"] = _clip(1 - abs((pr - er) / abs(er)))

    weights = {"reproducibility": 0.1, "walk_forward": 0.12, "random_baseline": 0.08,
               "out_of_sample": 0.12, "transaction_cost": 0.1, "liquidity": 0.06,
               "failure_learning": 0.06, "portfolio_impact": 0.08, "paper_performance": 0.08,
               "evidence": 0.06, "documentation": 0.04, "confidence": 0.1}
    overall = round(sum(dims[k] * weights[k] for k in weights) * 100, 1)
    grade = "A" if overall >= 80 else "B" if overall >= 65 else "C" if overall >= 50 else "D"
    return {"strategy": name, "dimensions": dims, "overall_quality": overall, "grade": grade,
            "validation_complete": v["validation_complete"],
            "missing_validations": v["missing_validations"],
            "is_advisory": True, "is_decision": False,
            "note": "결정적 품질 점수 — validate_backtest/recall 재사용, 새 저장소 없음."}
