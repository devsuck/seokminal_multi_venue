"""Strategy Research Agent (P125) — 가설을 세우고 실험을 설계하며 과거 연구를 분석한다. **분석만.**

Uses: experiment_planner·backtest_bridge·paper_validation. Output: Strategy Research Plan. Tasks: 가설 수립·
실험 설계·과거 연구 분석. 새 지능/메모리 없음 — 기존 엔진 재사용. **백테스트 자동 실행 없음(외부·사람).**

원칙(문서 §Constitution, §P125): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


class StrategyResearcher:
    """전략 연구원 — 가설·실험·백테스트 잡·검증을 담은 Strategy Research Plan. RESEARCH_ONLY."""

    role = "specialist"
    level = "RESEARCH_ONLY"

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def plan(self, topic: str, *, limit: int = 3) -> dict:
        """토픽 → Strategy Research Plan(가설·실험·백테스트잡·검증·과거연구). 결정적·읽기전용."""
        t = (topic or "").strip()

        # 1) 가설 수립 — hypothesis_generator 재사용
        hypotheses = []
        try:
            from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator
            hyps = HypothesisGenerator(assistant=self._asst).generate(t, limit=limit)
            hypotheses = [h.to_dict() for h in hyps]
        except Exception:  # noqa: BLE001
            pass
        top = hypotheses[0] if hypotheses else {"statement": t}

        # 2) 실험 설계 — experiment_planner 재사용
        experiment = {}
        try:
            from jarvis.research_workflow.experiment_planner import ExperimentPlanner
            experiment = ExperimentPlanner().plan(top).to_dict()
        except Exception:  # noqa: BLE001
            pass

        # 3) 백테스트 잡(요청만, 자동 실행 없음) — backtest_bridge 재사용
        backtest_job = {}
        try:
            from jarvis.research_workflow.backtest_bridge import create_job, submit_for_human_run
            job = submit_for_human_run(create_job(top))
            backtest_job = job.to_dict()
        except Exception:  # noqa: BLE001
            pass

        # 4) 과거 연구 분석 — recall + mistake_check 재사용
        historical = {}
        try:
            assistant = self._asst
            if assistant is None:
                from jarvis.research_assistant.engine import ResearchAssistantEngine
                assistant = ResearchAssistantEngine()
            name = experiment.get("strategy_name") or t
            r = assistant.recall(name)
            mc = assistant.mistake_check(name)
            historical = {"prior_records": r.total_hits, "tried_before": r.tried_before,
                          "made_this_mistake": mc.get("made_this_mistake"),
                          "failure_count": mc.get("failure_count", 0)}
        except Exception:  # noqa: BLE001
            pass

        return {"topic": t, "hypotheses": hypotheses, "primary_hypothesis": top.get("statement", t),
                "experiment": experiment, "backtest_job": backtest_job,
                "validation_plan": [c["metric"] if isinstance(c, dict) else c
                                    for c in experiment.get("validation_checklist", [])],
                "historical_research": historical,
                "plan_type": "Strategy Research Plan",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("Strategy Research Plan(읽기전용) — 가설·실험·백테스트잡(사람 실행 대기)·검증·과거연구. "
                         "experiment_planner/backtest_bridge/paper_validation 재사용. 자동 실행 없음.")}


def plan(topic: str, *, assistant=None, limit: int = 3) -> dict:
    """모듈 진입점 — StrategyResearcher.plan 래퍼."""
    return StrategyResearcher(assistant=assistant).plan(topic, limit=limit)
