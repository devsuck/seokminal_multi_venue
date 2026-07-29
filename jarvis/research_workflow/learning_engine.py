"""Institutional Learning Engine (P136) — 연구 결과를 **조직 교훈**으로 변환한다. **기존 메모리 경로로 저장.**

Input: experiment result·validation·failure. Output: Lesson {what happened·why·when applicable·when invalid}.
**재사용**: research_memory_intelligence.record_lesson(rmi_lessons) + validation_gap/forward_testing(원인)·
StrategyRiskReasoner(리스크). 새 저장소 없음 — 기존 rmi_ write 경로. commit=False=프리뷰.

원칙(문서 §Constitution, §P136): 통합·조율만. 결정적. 거래·집행 없음. 사람 검토.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ResearchLearningEngine:
    """조직 학습 엔진 — 결과/검증/실패 → 구조화 교훈 → 기존 rmi_ 저장. 실행 권한 없음."""

    def learn(self, *, backtest: dict | None = None, paper: dict | None = None,
              outcome: str = "", assistant=None, now: str = "", commit: bool = False) -> dict:
        """결과/검증/실패 → Lesson(무엇·왜·적용가능·무효조건) + 기존 rmi_ 저장(프리뷰 기본). 결정적."""
        bt = backtest or {}
        name = str(bt.get("strategy_name", "") or "research")
        m = bt.get("metrics") or {}

        # 원인(why) — validation_gap/forward_testing 재사용(페이퍼 있으면)
        why, gap = "", {}
        if paper is not None:
            gap = _safe(lambda: __import__("jarvis.research_workflow.validation_gap",
                                           fromlist=["analyze_gap"]).analyze_gap(bt, paper), {}) or {}
            causes = gap.get("possible_causes", [])
            why = "; ".join(c.get("cause", "") for c in causes[:2]) or "특이 원인 없음"
        # 리스크(무효 조건) — StrategyRiskReasoner 재사용
        risk = _safe(lambda: __import__("jarvis.research_risk_intelligence.failure_reasoning",
                                        fromlist=["StrategyRiskReasoner"]).StrategyRiskReasoner()
                     .risk_report(name, m).to_dict(), {})

        # 결과 라벨
        ret = _num(m.get("return"))
        label = (outcome or ("SUCCESS" if (ret is not None and ret > 0 and not gap.get("finding"))
                             else "FAILURE" if gap.get("finding", "").startswith("Paper") else "PARTIAL"))
        lesson = {
            "strategy": name,
            "what_happened": f"{name}: outcome={label}, return={m.get('return')}, sharpe={m.get('sharpe')}",
            "why": why or (risk.get("weakness") or "검증 대기"),
            "when_applicable": self._applicable(risk, m),
            "when_invalid": self._invalid(risk, gap),
            "outcome": label,
        }
        stored = self._store(name, lesson, evidence={"metrics": m, "gap": gap.get("finding", "")},
                             impact=label.lower(), now=now, commit=commit, assistant=assistant)
        return {"lesson": lesson, "stored": stored, "committed": commit,
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("조직 교훈(읽기전용 프리뷰) — 결과→교훈, 기존 rmi_lessons 저장(commit 시). "
                         "record_lesson 재사용, 새 저장소 없음.")}

    def _applicable(self, risk, m) -> str:
        strengths = risk.get("strength", "documented edge")
        return f"강점 구간: {strengths}" + (f"; walk_forward≥0.5" if _num(m.get("walk_forward")) else "")

    def _invalid(self, risk, gap) -> str:
        label = risk.get("main_risk_label", "model risk")
        if gap.get("gaps", {}).get("regime", {}).get("regime_mismatch"):
            return f"레짐 전환 시 무효; 주의: {label}"
        return f"무효 조건 — {label}; 비용/유동성 악화 시"

    def _store(self, name, lesson, *, evidence, impact, now, commit, assistant) -> dict:
        """기존 rmi_ record_lesson 경로로 저장(새 저장소 없음). 텍스트로 직렬화."""
        try:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            text = (f"LESSON [{name}] what={lesson['what_happened']} · why={lesson['why']} · "
                    f"applicable={lesson['when_applicable']} · invalid={lesson['when_invalid']}")
            rec = ResearchMemoryIntelligenceEngine().record_lesson(
                name, text, evidence=evidence, impact=impact, now=now, commit=commit)
            d = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
            return {"lesson_id": d.get("lesson_id"), "ledger": "rmi_lessons", "committed": commit}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def learn(*, backtest=None, paper=None, outcome="", assistant=None, now="", commit=False) -> dict:
    """모듈 진입점 — ResearchLearningEngine.learn 래퍼."""
    return ResearchLearningEngine().learn(backtest=backtest, paper=paper, outcome=outcome,
                                          assistant=assistant, now=now, commit=commit)
