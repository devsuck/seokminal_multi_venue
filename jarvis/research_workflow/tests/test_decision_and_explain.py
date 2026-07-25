"""Decision Support(P65) + Explainability(P67) 테스트 — 모든 섹션·역사참조·신뢰도·자문·안전.

핵심(문서 §Tests #3,#4): Decision Memo 가 필수 섹션을 모두 포함 · Explainability 가 과거 실험을 참조.
"""
from __future__ import annotations

import pytest

from jarvis.research_assistant import ledger as al
from jarvis.research_assistant.engine import ResearchAssistantEngine
from jarvis.research_workflow.decision_support import DecisionSupportEngine
from jarvis.research_workflow.explainability import ExplainabilityEngine

NOW = "2026-01-01T00:00:00Z"
DATA = {"experiments": [{"name": "momentum study"}],
        "experiment_runs": [{"note": "momentum edge"}],
        "successes": [{"id": "momentum win"}],
        "failures": [{"reason": "momentum overfit"}, {"reason": "momentum regime"}]}
_FULL = {"sharpe": 0.9, "return": 0.1, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}
_BT = {"strategy_name": "momentum", "metrics": dict(_FULL)}

_REQUIRED_SECTIONS = ("question", "evidence", "supporting_arguments", "counter_arguments",
                      "historical_similar_cases", "portfolio_impact", "risk_summary",
                      "confidence", "remaining_unknowns", "suggested_next_research",
                      "requires_human_review")


@pytest.fixture()
def asst():
    return ResearchAssistantEngine(reader=lambda n: DATA.get(n, []))


# ── 3. Decision Memo 모든 섹션 ──
def test_decision_memo_all_sections(asst):
    memo = DecisionSupportEngine(assistant=asst).build_memo(
        "Should we deploy momentum?", topic="momentum", metrics=_FULL, backtest=_BT)
    d = memo.to_dict()
    for s in _REQUIRED_SECTIONS:
        assert s in d, s
    assert d["requires_human_review"] is True
    assert d["is_decision"] is False


def test_decision_memo_explains_itself(asst):
    memo = DecisionSupportEngine(assistant=asst).build_memo("Q", topic="momentum", backtest=_BT)
    assert memo.rationale                      # 권고가 스스로를 설명
    assert memo.confidence in ("LOW", "MEDIUM", "HIGH")
    assert memo.confidence_breakdown


def test_decision_memo_historical_cases(asst):
    memo = DecisionSupportEngine(assistant=asst).build_memo("Q", topic="momentum")
    assert memo.historical_similar_cases       # 과거 유사 사례 포함


def test_decision_memo_supporting_and_counter(asst):
    memo = DecisionSupportEngine(assistant=asst).build_memo("Q", topic="momentum")
    # 지지·반대 논거가 협의체에서 나온다
    assert isinstance(memo.supporting_arguments, list)
    assert isinstance(memo.counter_arguments, list)


def test_decision_record_advisory_note(tmp_path, monkeypatch, asst):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(al, "state_path", lambda n: str(state / n))
    memo = DecisionSupportEngine(assistant=asst).build_memo("Q", topic="momentum")
    rec = DecisionSupportEngine(assistant=asst).record_memo(memo, now=NOW, commit=True)
    assert rec["is_binding"] is False          # 비구속(사람 승인 필요)


def test_decision_deterministic(asst):
    a = DecisionSupportEngine(assistant=asst).build_memo("Q", topic="momentum").to_dict()
    b = DecisionSupportEngine(assistant=asst).build_memo("Q", topic="momentum").to_dict()
    assert a == b


# ── 4. Explainability 과거 실험 참조 ──
def test_evidence_chain_references_experiments(asst):
    ec = ExplainabilityEngine(assistant=asst).evidence_chain("momentum", backtest=_BT)
    assert ec.references_experiments           # 실제 실험 참조
    assert "momentum study" in ec.references_experiments


def test_evidence_chain_full_pipeline(asst):
    ec = ExplainabilityEngine(assistant=asst).evidence_chain("momentum")
    stages = [n["stage"] for n in ec.chain]
    assert stages[0] == "Experiment"
    assert stages[-1] == "Final Recommendation"
    assert len(ec.edges) == len(stages) - 1


def test_evidence_chain_explains_all(asst):
    ec = ExplainabilityEngine(assistant=asst).evidence_chain("momentum", backtest=_BT)
    d = ec.to_dict()
    assert d["why_this_conclusion"]
    assert d["why_it_may_be_wrong"]
    assert d["alternative_interpretations"]
    assert "missing_evidence" in d
    assert d["confidence_breakdown"]


def test_evidence_chain_not_black_box(asst):
    ec = ExplainabilityEngine(assistant=asst).evidence_chain("momentum")
    assert ec.is_decision is False
    assert ec.requires_human_review is True


def test_incomplete_backtest_surfaces_missing(asst):
    ec = ExplainabilityEngine(assistant=asst).evidence_chain(
        "momentum", backtest={"strategy_name": "m", "metrics": {"sharpe": 0.5}})
    assert any("Incomplete validation" in u for u in ec.missing_evidence)
