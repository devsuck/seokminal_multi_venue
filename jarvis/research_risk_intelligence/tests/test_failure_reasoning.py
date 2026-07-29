"""Risk Intelligence(P62) 테스트 — 실패 시나리오·6범주·Risk Report·메모리 연결·자문·안전.

핵심(문서 §Tests #3,#4): Risk Report 생성 + 실패 시나리오 기록.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_risk_intelligence.failure_reasoning import (
    RISK_CATEGORIES,
    StrategyRiskReasoner,
)

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

_FULL = {"return": 0.14, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
    return StrategyRiskReasoner(ResearchMemoryIntelligenceEngine())


# ── 실패 시나리오: "무엇이 이걸 실패시키는가?" ──
def test_failure_scenarios_cover_six_categories(env):
    sc = env.failure_scenarios("Momentum", _FULL)
    cats = {s.category for s in sc}
    assert set(RISK_CATEGORIES) <= cats     # Market/Liquidity/Model/Data/Regime/Concentration


def test_momentum_failure_scenarios_expected(env):
    sc = env.failure_scenarios("Momentum", _FULL)
    scenarios = " ".join(s.scenario.lower() for s in sc)
    assert "volatility expansion" in scenarios    # 1
    assert "regime reversal" in scenarios          # 2
    assert "crowded positioning" in scenarios      # 3
    assert "transaction cost" in scenarios or "liquidity" in scenarios  # 4


# ── Risk Report ──
def test_tsmom_risk_report(env):
    rep = env.risk_report("TSMOM", _FULL)
    assert rep.strategy_type == "trend"
    assert rep.strength == "Trend persistence"
    assert "reversal" in rep.weakness.lower()
    assert rep.main_risk == "REGIME"
    assert rep.confidence in ("LOW", "MEDIUM", "HIGH")


def test_high_cost_promotes_liquidity_risk(env):
    rep = env.risk_report("SomeGeneric", {**_FULL, "cost_impact": 0.5})
    assert rep.category_flags.get("LIQUIDITY") == "HIGH"


def test_incomplete_metrics_low_confidence(env):
    rep = env.risk_report("Momentum", {"sharpe": 0.3})
    assert rep.confidence == "LOW"


def test_factor_strategy_concentration(env):
    rep = env.risk_report("Value Factor", _FULL)
    assert rep.strategy_type == "factor"
    assert rep.category_flags.get("CONCENTRATION") == "HIGH"


# ── 메모리 연결(recall 회수) ──
def test_record_risk_report_reaches_memory(env):
    rep = env.risk_report("TSMOM", _FULL)
    env.record_risk_report(rep, experiment_id="XT:exp1", now="2026-01-01T00:00:00Z", commit=True)
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_lessons()) == 1
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    assert ResearchAssistantEngine().recall("TSMOM").tried_before is True


def test_report_advisory(env):
    rep = env.risk_report("Momentum", _FULL)
    d = rep.to_dict()
    assert d["is_advisory"] is True and d["is_decision"] is False
    assert d["requires_human_review"] is True


def test_deterministic(env):
    assert env.risk_report("TSMOM", _FULL).to_dict() == env.risk_report("TSMOM", _FULL).to_dict()


# ── 안전 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "failure_reasoning.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "failure_reasoning.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "failure_reasoning.py").read().lower()
