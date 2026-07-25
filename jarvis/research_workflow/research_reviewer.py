"""Research Critic Agent (P126) — 기존 critic 을 확장한 리뷰어. **연구를 도전(challenge)한다, 결정 없음.**

평가: bias·overfitting·missing evidence·weak assumptions·validation quality. **재사용**: ResearchCritic(P75,
8차원)·quality_monitor(P106)·StrategyRiskReasoner(P62 실패 분류체계)·classify_failure(9-way taxonomy).
Output: Research Review. 새 지능/메모리 없음 — 기존 비판 엔진 확장.

원칙(문서 §Constitution, §P126): 통합·조율만. 결정적. 거래·집행 없음. 자동 수용 없음.
"""
from __future__ import annotations


class ResearchReviewer:
    """연구 리뷰어 — 편향·과적합·누락증거·약한가정·검증품질을 비판한 Research Review. RESEARCH_ONLY."""

    role = "critic"
    level = "RESEARCH_ONLY"

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def review(self, spec, *, metrics: dict | None = None) -> dict:
        """실험 스펙/결과 → Research Review(critique + quality + risk + 종합 verdict). 결정적."""
        s = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec or {})
        m = metrics or s.get("metrics") or {}
        name = str(s.get("strategy_name", "") or "experiment")

        # 1) 8차원 비판 — ResearchCritic(P75) 재사용
        critique = _safe(lambda: __import__("jarvis.research_workflow.research_critic",
                                            fromlist=["ResearchCritic"]).ResearchCritic()
                         .critique(s, m).to_dict(), {"critiques": [], "verdict": "WARN"})
        # 2) 품질/누락증거 — quality_monitor(P106) 재사용
        quality = _safe(lambda: __import__("jarvis.research_workflow.quality_monitor",
                                           fromlist=["evaluate"]).evaluate({**s, "metrics": m},
                        assistant=self._asst), {"grade": "D", "missing_validations": []})
        # 3) 리스크(실패 분류체계) — StrategyRiskReasoner(P62) 재사용
        risk = _safe(lambda: __import__("jarvis.research_risk_intelligence.failure_reasoning",
                                        fromlist=["StrategyRiskReasoner"]).StrategyRiskReasoner()
                     .risk_report(name, m).to_dict(), {"main_risk": "MODEL"})

        # 4) 스펙 요구 차원 — bias·missing evidence·weak assumptions·validation quality(결정적 파생)
        dims = self._assess(critique, quality, risk, m)

        verdict = ("BLOCK" if critique.get("blocks") or dims["validation_quality"] == "WEAK"
                   else "WARN" if critique.get("verdict") == "WARN" or dims["overfitting_risk"] != "LOW"
                   else "PASS")
        return {"subject": name, "critique": critique,
                "dimensions": dims,
                "quality": {"grade": quality.get("grade"), "score": quality.get("quality_score"),
                            "weaknesses": quality.get("weaknesses", []),
                            "missing_validations": quality.get("missing_validations", [])},
                "risk": {"main_risk": risk.get("main_risk"), "main_risk_label": risk.get("main_risk_label"),
                         "weakness": risk.get("weakness")},
                "verdict": verdict, "blocks": verdict == "BLOCK",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("Research Review(읽기전용) — bias·overfitting·missing evidence·weak assumptions·"
                         "validation quality. ResearchCritic/quality_monitor/risk 재사용. 자동 수용 없음.")}

    def _assess(self, critique, quality, risk, metrics) -> dict:
        """스펙 요구 5차원(결정적) — 기존 산출에서 파생, 새 지능 없음."""
        crit_by = {c["dimension"]: c["severity"] for c in critique.get("critiques", [])}
        overfit = crit_by.get("overfitting", "WARN")
        missing = quality.get("missing_validations", []) or []
        weak = quality.get("weaknesses", []) or []
        return {
            "bias": ("HIGH" if crit_by.get("survivorship") == "BLOCK" or crit_by.get("look_ahead") == "BLOCK"
                     else "MEDIUM" if crit_by.get("survivorship") == "WARN" else "LOW"),
            "overfitting_risk": ("HIGH" if overfit == "BLOCK" else "MEDIUM" if overfit == "WARN" else "LOW"),
            "missing_evidence": missing,
            "weak_assumptions": weak,
            "validation_quality": ("WEAK" if quality.get("grade") in ("C", "D") or missing
                                   else "ADEQUATE" if quality.get("grade") == "B" else "STRONG"),
        }


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def review(spec, *, metrics: dict | None = None, assistant=None) -> dict:
    """모듈 진입점 — ResearchReviewer.review 래퍼."""
    return ResearchReviewer(assistant=assistant).review(spec, metrics=metrics)
