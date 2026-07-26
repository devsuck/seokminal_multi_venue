"""Strategy Health Monitoring (P144) — 연구된 전략의 건강을 감시한다. **읽기 전용, 신호 아님.**

분석: performance changes·validation status·regime compatibility·risk changes·historical similarity.
출력: StrategyHealthReport {strategy, health_score, warnings, historical_context, review_needed}.
**재사용**: quality_monitor(P106)·strategy_lifecycle(P105)·StrategyRiskReasoner(P62)·regime·strategy_lab/recall.

원칙(문서 §Constitution, §P144): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


class StrategyHealthMonitor:
    """전략 건강 모니터 — 성과·검증·레짐·리스크·과거유사 → StrategyHealthReport. RESEARCH_ONLY."""

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def report(self, strategy: str, *, metrics: dict | None = None, market: dict | None = None) -> dict:
        """전략 → StrategyHealthReport(건강점수·경고·과거·검토필요). 결정적·읽기전용."""
        name = (strategy or "").strip()
        m = metrics or {}
        warnings = []

        # 1) 품질/검증 상태 — quality_monitor
        quality = _safe(lambda: __import__("jarvis.research_workflow.quality_monitor",
                                           fromlist=["evaluate"]).evaluate({"strategy_name": name,
                        "metrics": m}, assistant=self._asst), {"quality_score": 0, "grade": "D"})
        if quality.get("grade") in ("C", "D"):
            warnings.append(f"낮은 품질 등급({quality.get('grade')})")
        if quality.get("missing_validations"):
            warnings.append(f"미검증: {', '.join(quality['missing_validations'][:3])}")

        # 2) 생애주기 상태 — strategy_lifecycle
        lifecycle = _safe(lambda: __import__("jarvis.research_workflow.strategy_lifecycle",
                                             fromlist=["lifecycle_state"]).lifecycle_state(name),
                          {"current_state": "DISCOVERED"})

        # 3) 리스크 변화 — StrategyRiskReasoner
        risk = _safe(lambda: __import__("jarvis.research_risk_intelligence.failure_reasoning",
                                        fromlist=["StrategyRiskReasoner"]).StrategyRiskReasoner()
                     .risk_report(name, m).to_dict(), {})
        if risk.get("main_risk"):
            warnings.append(f"주요 리스크: {risk.get('main_risk_label', risk['main_risk'])}")

        # 4) 레짐 호환성 — regime
        regime = _safe(lambda: __import__("jarvis.research_workflow.regime", fromlist=["detect_regime"])
                       .detect_regime(market or {}, assistant=self._asst), {"regime": "UNKNOWN"})

        # 5) 과거 유사 — recall + mistake_check
        historical = _safe(lambda: _hist(self._asst, name), {})
        if historical.get("made_this_mistake"):
            warnings.append(f"과거 동일 실패 {historical.get('failure_count', 0)}회")

        # 건강 점수 — 품질 - 경고 페널티
        base = float(quality.get("quality_score", 0) or 0)
        health = round(max(0.0, base - len(warnings) * 8.0), 1)
        review_needed = bool(warnings or health < 65 or lifecycle.get("current_state") == "PAPER")
        return {"strategy": name or "unknown", "health_score": health,
                "quality_grade": quality.get("grade"),
                "lifecycle_state": lifecycle.get("current_state"),
                "regime_compatibility": {"current_regime": regime.get("regime")},
                "risk": {"main_risk": risk.get("main_risk"), "label": risk.get("main_risk_label")},
                "warnings": warnings, "historical_context": historical,
                "review_needed": review_needed,
                "report_type": "StrategyHealthReport",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("StrategyHealthReport(읽기전용) — 성과·검증·레짐·리스크·과거. 신호 아님. "
                         "quality_monitor/lifecycle/risk/regime 재사용, 새 저장소 없음.")}

    def board(self, *, strategies: list | None = None, limit: int = 20) -> dict:
        """전 전략 건강 보드 — strategy_lifecycle 파생 이름으로 각 건강 리포트(읽기전용)."""
        try:
            from jarvis.research_workflow.strategy_lifecycle import _known_strategies
            names = strategies if strategies else _known_strategies(limit)
        except Exception:  # noqa: BLE001
            names = strategies or []
        rows = [self.report(n) for n in names]
        return {"strategies": [{"strategy": r["strategy"], "health_score": r["health_score"],
                                "grade": r["quality_grade"], "warnings": len(r["warnings"]),
                                "review_needed": r["review_needed"]} for r in rows],
                "count": len(rows), "review_needed_count": sum(1 for r in rows if r["review_needed"]),
                "is_advisory": True, "is_decision": False,
                "note": "전략 건강 보드(읽기전용) — 새 저장소 없음."}


def _hist(assistant, name):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(name)
    mc = assistant.mistake_check(name)
    return {"prior_records": r.total_hits, "tried_before": r.tried_before,
            "made_this_mistake": mc.get("made_this_mistake"), "failure_count": mc.get("failure_count", 0)}


def report(strategy: str, *, metrics=None, market=None, assistant=None) -> dict:
    """모듈 진입점 — StrategyHealthMonitor.report 래퍼."""
    return StrategyHealthMonitor(assistant=assistant).report(strategy, metrics=metrics, market=market)
