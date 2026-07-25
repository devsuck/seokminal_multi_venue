"""P73 Hypothesis Generator + P74 Experiment Planner 테스트 — 생성·구조·저장/회상·재현성·안전."""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_assistant import ledger as al
from jarvis.research_assistant.engine import ResearchAssistantEngine
from jarvis.research_memory_intelligence import ledger as ml
from jarvis.research_workflow.experiment_planner import ExperimentPlanner
from jarvis.research_workflow.hypothesis_generator import Hypothesis, HypothesisGenerator

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

DATA = {"experiments": [{"name": "momentum study"}, {"name": "insider signal"},
                        {"name": "liquidity factor"}],
        "experiment_runs": [{"note": "insider edge"}, {"note": "liquidity screen"}],
        "failures": [{"reason": "cost sensitivity high"}, {"reason": "cost sensitivity turnover"}]}


@pytest.fixture()
def asst():
    return ResearchAssistantEngine(reader=lambda n: DATA.get(n, []))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda n: str(state / n)  # noqa: E731
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return HypothesisGenerator(assistant=ResearchAssistantEngine(reader=lambda n: DATA.get(n, [])),
                               memory_engine=None)


# ── P73 ──
def test_generate_hypotheses(asst):
    hyps = HypothesisGenerator(assistant=asst).generate(topic="momentum", limit=6)
    assert len(hyps) >= 1
    h = hyps[0]
    assert h.statement and h.rationale
    assert h.expected_edge in ("LOW", "MEDIUM", "HIGH")
    assert h.assumptions and h.invalidation_conditions      # 필수 필드


def test_generate_includes_supply_chain(asst):
    hyps = HypothesisGenerator(assistant=asst).generate(topic="x", limit=8)
    assert any(h.source == "supply_chain" for h in hyps)


def test_generate_portfolio_hypothesis(asst):
    hyps = HypothesisGenerator(assistant=asst).generate(topic="x", portfolio={"exposures": {}}, limit=8)
    assert any(h.source == "portfolio" for h in hyps)


def test_generate_deterministic(asst):
    a = [h.hypothesis_id for h in HypothesisGenerator(assistant=asst).generate(topic="momentum", limit=6)]
    b = [h.hypothesis_id for h in HypothesisGenerator(assistant=asst).generate(topic="momentum", limit=6)]
    assert a == b


# ── P73 저장/회상 (기존 메모리 인프라) ──
def test_hypothesis_persisted_and_recalled(env):
    hyps = env.generate(topic="momentum", limit=4)
    env.store(hyps[0], now=NOW, commit=True)
    assert len(ml.read_lessons()) == 1
    # recall 이 저장된 가설을 찾는다
    asst = ResearchAssistantEngine()
    r = asst.recall(hyps[0].statement.split()[0])
    assert r.tried_before is True


def test_store_dry_run_no_write(env):
    hyps = env.generate(topic="momentum", limit=2)
    env.store(hyps[0], now=NOW, commit=False)
    assert ml.read_lessons() == []


# ── P74 Experiment Planner ──
def _hyp():
    return Hypothesis(hypothesis_id="RHYP:x", statement="Momentum produces a persistent edge",
                      rationale="r", expected_edge="MEDIUM", assumptions=["a"],
                      invalidation_conditions=["i"], source="queue:COMBINATION", confidence="MEDIUM")


def test_plan_defines_all_fields():
    spec = ExperimentPlanner().plan(_hyp())
    for f in ("universe", "timeframe", "rebalance", "feature_set", "labels",
              "transaction_costs", "walk_forward", "random_baseline", "validation_checklist"):
        assert getattr(spec, f), f


def test_plan_validation_checklist_reuses_required():
    from jarvis.research_ingestion.models import REQUIRED_VALIDATIONS
    spec = ExperimentPlanner().plan(_hyp())
    metrics = [c["metric"] for c in spec.validation_checklist]
    assert set(metrics) == set(REQUIRED_VALIDATIONS)
    assert all(c["status"] == "PENDING" for c in spec.validation_checklist)


def test_plan_reproducible():
    a = ExperimentPlanner().plan(_hyp())
    b = ExperimentPlanner().plan(_hyp())
    assert a.spec_hash == b.spec_hash
    assert a.to_dict() == b.to_dict()


def test_plan_momentum_profile():
    spec = ExperimentPlanner().plan(_hyp())
    assert spec.universe == "GLOBAL_FUT" and spec.rebalance == "monthly"
    assert "ret_12m" in spec.feature_set


def test_plan_to_ingestion_schema():
    spec = ExperimentPlanner().plan(_hyp())
    sch = spec.to_ingestion_schema()
    assert sch["strategy_name"] and sch["metrics"] == {}   # 실행 전 — INCOMPLETE
    assert sch["source"] == "experiment_planner"


def test_plan_advisory():
    spec = ExperimentPlanner().plan(_hyp())
    assert spec.is_advisory is True and spec.is_decision is False


# ── 안전 ──
def test_no_forbidden_imports_defs_leak():
    for f in ("hypothesis_generator.py", "experiment_planner.py"):
        src = open(SRC / f).read()
        assert MODEL_LEAK_TOKEN not in src.lower()
        tree = ast.parse(src)
        bad_imp = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                   "jarvis.live_trading", "jarvis.portfolio_execution")
        bad_def = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in bad_imp), (f, node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in bad_def, (f, node.name)
