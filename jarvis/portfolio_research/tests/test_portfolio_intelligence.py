"""Portfolio Intelligence(P61) 테스트 — 노출·조합·상관·포트폴리오 메모리·자문·안전.

핵심(문서 §Tests #1,#2): 포트폴리오 영향 분석·상관 분석이 동작하고, 관찰이 recall 로 회수된다.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.portfolio_research.intelligence import PortfolioIntelligence, pearson

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """rmi_·research_assistant 원장을 같은 tmp _state 로 격리(포트폴리오 메모리 검증)."""
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
    return PortfolioIntelligence(ResearchMemoryIntelligenceEngine())


# ── 노출 분석 ──
def test_exposure_concentration_increase(env):
    new = {"name": "Semiconductor Momentum",
           "exposures": {"sector": {"semiconductor": 0.8, "hardware": 0.2}}}
    pf = {"exposures": {"sector": {"semiconductor": 0.35, "software": 0.3, "financials": 0.35}},
          "weight_new": 0.2, "correlation": 0.7}
    rep = env.exposure_analysis(new, pf)
    semi = rep.by_dimension["sector"]["semiconductor"]
    assert semi["after"] > semi["before"]          # 35% → 상승
    assert semi["concentration"] is True           # 0.44 ≥ 0.40
    assert rep.additional_correlation == "HIGH"
    assert any("Concentration increase" in f for f in rep.risk_flags)


def test_exposure_low_correlation_diversifies(env):
    new = {"name": "Bond Carry", "exposures": {"sector": {"rates": 0.9}}}
    pf = {"exposures": {"sector": {"semiconductor": 0.35, "software": 0.3}},
          "weight_new": 0.1, "correlation": 0.05}
    rep = env.exposure_analysis(new, pf)
    assert rep.additional_correlation == "LOW"
    assert rep.risk_flags == []


# ── 조합 분석 ──
def test_combination_low_correlation_benefit(env):
    strategies = [
        {"name": "Momentum", "correlation_to": {"Value": 0.1}, "max_drawdown": -0.2,
         "regimes": ["trending"]},
        {"name": "Value", "correlation_to": {"Momentum": 0.1}, "max_drawdown": -0.18,
         "regimes": ["ranging"]},
    ]
    rep = env.combination_analysis(strategies)
    p = rep.pairs[0]
    assert p["correlation"] == 0.1
    assert p["diversification"] == "BENEFIT"
    assert "분산" in rep.verdict


def test_combination_from_returns_correlation():
    # 수익률로 직접 상관 계산(피어슨)
    assert pearson([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert pearson([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert pearson([1], [1]) is None               # 표본 부족


def test_combination_redundant_high_corr(env):
    strategies = [{"name": "A", "correlation_to": {"B": 0.9}},
                  {"name": "B", "correlation_to": {"A": 0.9}}]
    rep = env.combination_analysis(strategies)
    assert rep.pairs[0]["diversification"] == "REDUNDANT"


# ── 포트폴리오 메모리(Strategy→Experiment→Portfolio Effect→Lesson) ──
def test_record_portfolio_impact_reaches_memory(env):
    new = {"name": "Semiconductor Momentum",
           "exposures": {"sector": {"semiconductor": 0.8}}}
    pf = {"exposures": {"sector": {"semiconductor": 0.35}}, "weight_new": 0.2, "correlation": 0.7}
    rep = env.exposure_analysis(new, pf)
    env.record_portfolio_impact("Semiconductor Momentum", "XT:exp1", rep.to_dict(),
                                now="2026-01-01T00:00:00Z", commit=True)
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_lessons()) == 1
    # recall 이 찾는다
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    r = ResearchAssistantEngine().recall("Semiconductor Momentum")
    assert r.tried_before is True


def test_reports_advisory(env):
    rep = env.exposure_analysis({"name": "X", "exposures": {}}, {"exposures": {}})
    assert rep.is_advisory is True and rep.is_decision is False
    assert rep.requires_human_review is True


def test_deterministic(env):
    new = {"name": "X", "exposures": {"sector": {"a": 0.5}}}
    pf = {"exposures": {"sector": {"a": 0.3}}, "weight_new": 0.2}
    assert env.exposure_analysis(new, pf).to_dict() == env.exposure_analysis(new, pf).to_dict()


# ── 안전 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "intelligence.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "intelligence.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "intelligence.py").read().lower()
