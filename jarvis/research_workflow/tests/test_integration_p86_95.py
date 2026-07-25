"""P86-95 시장 지능 오케스트레이션 테스트 — 이벤트·레짐·기회·대체데이터·협의체·전략랩·시뮬·위원회·포워드·콕핏.

핵심: 모두 기존 엔진/원장 재사용 · 새 원장/엔진 없음 · 결정적 · 거래·집행·신호 없음.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_assistant import ledger as al
from jarvis.research_ingestion import ledger as ringl
from jarvis.research_memory_intelligence import ledger as ml
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow.alt_data import ALT_SOURCES, catalog, observe
from jarvis.research_workflow.council_evolution import deliberate as council_deliberate
from jarvis.research_workflow.decision_center import committee_packet
from jarvis.research_workflow.event_stream import classify_event, stream
from jarvis.research_workflow.forward_testing import analyze as forward_analyze
from jarvis.research_workflow.market_cockpit import build_market_cockpit
from jarvis.research_workflow.opportunity_discovery import discover
from jarvis.research_workflow.portfolio_sim import simulate
from jarvis.research_workflow.regime import classify, detect_regime
from jarvis.research_workflow.strategy_lab import repeated_mistakes, strategy_dna

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("event_stream.py", "regime.py", "opportunity_discovery.py", "alt_data.py",
            "council_evolution.py", "strategy_lab.py", "portfolio_sim.py", "decision_center.py",
            "forward_testing.py", "market_cockpit.py")


# ── P86 Event Stream ──
def test_event_classified_and_affected():
    e = classify_event({"kind": "news", "text": "Taiwan earthquake", "entity": "Taiwan"})
    assert e["event_type"] == "NEWS"
    assert "TSMC" in e["affected_entities"]
    assert e["requires_human_review"] is True and e["is_decision"] is False


def test_event_stream_batch():
    s = stream([{"kind": "earnings", "entity": "NVDA"}, {"kind": "insider", "entity": "AAPL"}])
    assert s["count"] == 2
    assert len(s["human_review_queue"]) == 2


# ── P87 Regime ──
def test_regime_classify_labels():
    labels, conf = classify({"trend_strength": 0.2, "volatility": 0.4, "liquidity": -1,
                             "inflation": 0.05, "risk_appetite": -1})
    assert "VOLATILITY_SHOCK" in labels and "RISK_OFF" in labels and "LIQUIDITY_CONTRACTION" in labels
    assert conf == 1.0


def test_regime_historical_and_strategies():
    r = detect_regime({"volatility": 0.4, "liquidity": -1, "risk_appetite": -1, "inflation": 0.05})
    assert any(p["period"] in ("2008", "2022") for p in r["historical_similar_periods"])
    assert r["favorable_strategies"] and r["unfavorable_strategies"]
    assert r["is_decision"] is False


def test_regime_unknown_without_indicators():
    assert detect_regime({})["regime"] == "UNKNOWN"


# ── P88 Opportunity Discovery ──
def test_opportunity_research_idea_only():
    o = discover({"insider_anomaly": {"entity": "NVDA", "evidence": ["cluster", "10 insiders", "3x avg"]}})
    op = o["opportunities"][0]
    assert op["is_trade_signal"] is False and op["is_research_idea"] is True
    assert op["confidence"] == "HIGH"
    assert op["suggested_hypothesis"]


def test_opportunity_types():
    o = discover({"supply_disruption": {"entity": "TSMC"}, "sentiment_extreme": {"entity": "TSLA"}})
    assert o["count"] == 2


# ── P89 Alt Data ──
def test_alt_data_catalog():
    c = catalog()
    assert c["count"] == len(ALT_SOURCES) == 7
    assert "shipping" in c["sources"]


def test_alt_data_observe_maps_entity():
    r = observe("hiring", "NVDA", value=1200, direction="up")
    assert r["maps_to"] == "company"
    assert r["is_trade_signal"] is False


def test_alt_data_unknown_source():
    assert "error" in observe("bogus", "X")


# ── P90 Council Evolution ──
def test_council_seven_perspectives():
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine(reader=lambda n: {"experiments": [{"name": "momentum"}],
                                                     "failures": [{"reason": "momentum regime"}]}.get(n, []))
    c = council_deliberate("momentum thesis", assistant=asst)
    assert len(c["expanded_perspectives"]) == 7
    names = {ln["lens"] for ln in c["lenses"]}
    assert {"Industry", "Behavioral", "Contrarian", "Portfolio"} <= names
    assert c["is_decision"] is False


# ── P91 Strategy Lab ──
def test_strategy_dna():
    dna = strategy_dna("momentum", spec={"universe": "KR", "features": ["ret_12m"],
                                         "entry_rules": "top decile", "timeframe": "1d"})
    assert dna["type"] == "trend"
    assert dna["dna"]["factors"] == ["ret_12m"]
    assert dna["dna"]["time_horizon"] == "1d"
    assert "failure_history" in dna["dna"]
    assert dna["is_decision"] is False


def test_repeated_mistakes():
    r = repeated_mistakes("momentum")
    assert "made_this_mistake" in r


# ── P92 Portfolio Sim ──
def test_portfolio_sim():
    s = simulate([{"name": "A", "returns": [1, 2, 3, 4], "max_drawdown": -0.2, "regimes": ["RISK_ON"]},
                  {"name": "B", "returns": [4, 3, 2, 1], "max_drawdown": -0.15, "regimes": ["RISK_OFF"]}])
    assert "risk_concentration_hhi" in s
    assert s["expected"]["risk"] in ("LOW", "MEDIUM", "HIGH")
    assert s["expected"]["stress_scenarios"]
    assert s["is_decision"] is False


def test_portfolio_sim_needs_two():
    assert "note" in simulate([{"name": "A"}])


# ── P93 Decision Center ──
def test_committee_packet():
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine(reader=lambda n: [])
    p = committee_packet("Should we deploy momentum?", topic="momentum", assistant=asst)
    for k in ("thesis", "counter_arguments", "risk_summary", "confidence", "council",
              "decision_history", "requires_human_decision"):
        assert k in p, k
    assert p["is_decision"] is False


# ── P94 Forward Testing ──
def test_forward_analyze():
    a = forward_analyze({"return": 0.15, "cost_impact": 0.1}, {"return": 0.03, "cost_impact": 0.4})
    assert a["cost_assumption_error"] is True
    assert a["data_leakage_suspected"] is True
    assert a["findings"] and a["learning_feedback"]
    assert a["is_decision"] is False


# ── P95 Market Cockpit ──
def test_market_cockpit():
    c = build_market_cockpit({"volatility": 0.4, "risk_appetite": -1},
                             {"macro_shock": {"entity": "rates"}})
    for k in ("market_state", "research_opportunities", "active_experiments", "validation_status",
              "risk", "portfolio_context", "decision_queue", "knowledge_growth"):
        assert k in c, k
    assert c["is_decision"] is False


def test_market_cockpit_deterministic():
    a = build_market_cockpit({"volatility": 0.4}).get("market_state")
    b = build_market_cockpit({"volatility": 0.4}).get("market_state")
    assert a == b


# ── 중복 원장/엔진 없음 + 안전 ──
def test_no_new_ledger():
    assert wl.ALL_LEDGERS == (("rwf_runs.jsonl", "event_id"), ("rwf_sessions.jsonl", "event_id"),
                              ("rwf_loops.jsonl", "event_id"))


def test_no_forbidden_defs_imports_leak():
    for f in _MODULES:
        src = open(SRC / f).read()
        assert MODEL_LEAK_TOKEN not in src.lower()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in
                               ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                                "jarvis.live_trading", "jarvis.portfolio_execution")), (f, node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                         "place_order"), (f, node.name)
