"""P96-100 라이브 시장 지능 어댑터 테스트 — 시장데이터·뉴스·내부자·공급망·실적.

핵심: DATA → EVENT → RESEARCH CONTEXT → HUMAN REVIEW. 모두 기존 event_intelligence/recall 재사용 ·
새 원장/엔진/DB 없음 · 결정적 · 거래·집행·신호 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow.earnings_intelligence import analyze_earnings, stream as earnings_stream
from jarvis.research_workflow.insider_flow import analyze_transaction, stream as insider_stream
from jarvis.research_workflow.market_data_adapter import ingest, normalize
from jarvis.research_workflow.news_intelligence import analyze_headline, stream as news_stream
from jarvis.research_workflow.supply_chain_impact import propagate, relationship_graph

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("market_data_adapter.py", "news_intelligence.py", "insider_flow.py",
            "supply_chain_impact.py", "earnings_intelligence.py")


# ── P96 Market Data ──
def test_normalize_preserves_timestamp_source():
    ev = normalize({"asset": "AAPL", "return": 0.08, "timestamp": "2026-01-03T09:30:00Z"}, source="US")
    assert ev.source == "US" and ev.timestamp == "2026-01-03T09:30:00Z"
    assert ev.event_type == "PRICE_SURGE"
    assert set(ev.to_dict()) >= {"source", "asset", "timestamp", "event_type", "metrics",
                                 "confidence", "related_entities"}


def test_market_event_types():
    assert normalize({"asset": "X", "volatility": 0.5}).event_type == "VOLATILITY_SPIKE"
    assert normalize({"asset": "X", "return": -0.08}).event_type == "PRICE_DROP"
    assert normalize({"asset": "X", "volume_ratio": 3.0}).event_type == "VOLUME_SPIKE"
    assert normalize({"asset": "X", "return": 0.001}).event_type == "MARKET_UPDATE"


def test_market_ingest_to_research():
    r = ingest([{"asset": "AAPL", "return": 0.08}], source="US")
    assert r["count"] == 1
    assert r["research_events"][0]["requires_human_review"] is True
    assert r["is_decision"] is False


# ── P97 News ──
def test_news_supply_chain_classification():
    n = analyze_headline("TSMC supplier expands production capacity", entity="TSMC")
    assert n["event_type"] == "SUPPLY_CHAIN_CHANGE"
    assert "NVIDIA" in n["affected_companies"] or "Apple" in n["affected_companies"]
    assert n["relevance_score"] in ("LOW", "MEDIUM", "HIGH")
    assert n["is_trade_signal"] is False


def test_news_types():
    assert analyze_headline("Company beats earnings estimates")["event_type"] == "EARNINGS_NEWS"
    assert analyze_headline("Regulator opens antitrust probe")["event_type"] == "REGULATORY"


def test_news_stream():
    s = news_stream([{"text": "TSMC supplier expands", "entity": "TSMC"}, "generic headline"])
    assert s["count"] == 2 and len(s["review_queue"]) == 2


# ── P98 Insider ──
def test_insider_conviction():
    e = analyze_transaction({"entity": "NVDA", "type": "BUY", "role": "CEO",
                             "prior_return": -0.2, "size": 2e6, "source": "SEC_FORM4"})
    assert e.transaction_type == "CONVICTION_BUY"
    assert e.confidence == "HIGH"
    assert e.is_trade_signal is False and e.is_research_trigger is True


def test_insider_cluster():
    e = analyze_transaction({"entity": "AAPL", "type": "BUY", "n_insiders": 4, "prior_return": 0.1})
    assert e.transaction_type == "CLUSTER_BUY"


def test_insider_stream_triggers():
    s = insider_stream([{"entity": "X", "type": "BUY", "role": "CEO", "prior_return": -0.3, "size": 5e6}])
    assert s["count"] == 1
    assert s["research_triggers"]


# ── P99 Supply Chain ──
def test_supply_chain_propagation():
    r = propagate({"text": "TSMC production issue", "entity": "TSMC"})
    assert r["origin"] == "TSMC"
    assert len(r["affected_entities"]) >= 3
    assert any(a["category"] == "customer" for a in r["affected_entities"]) or r["customers"]
    assert all("uncertainty" in a for a in r["affected_entities"])
    assert r["is_decision"] is False


def test_supply_chain_extended_graph():
    g = relationship_graph()
    ids = {n["id"] for n in g["nodes"]}
    assert "AI_Server" in ids and "Power_Infra" in ids     # 참조 그래프 보강


def test_supply_chain_unknown_origin():
    assert propagate({"text": "random unrelated"})["origin"] == ""


# ── P100 Earnings ──
def test_earnings_positive_surprise():
    e = analyze_earnings({"company": "NVDA", "period": "2025Q4",
                          "expected": {"revenue": 10, "eps": 0.5}, "actual": {"revenue": 11.8, "eps": 0.62}})
    assert e["overall_surprise"] == "POSITIVE_SURPRISE"
    assert "post-earnings drift (PEAD)" in e["related_strategy_impact"]
    assert e["is_trade_signal"] is False


def test_earnings_negative_and_inline():
    neg = analyze_earnings({"company": "X", "expected": {"eps": 1.0}, "actual": {"eps": 0.8}})
    assert neg["overall_surprise"] == "NEGATIVE_SURPRISE"
    inl = analyze_earnings({"company": "Y", "expected": {"eps": 1.0}, "actual": {"eps": 1.01}})
    assert inl["overall_surprise"] == "IN_LINE"


def test_earnings_stream():
    s = earnings_stream([{"company": "NVDA", "expected": {"eps": 0.5}, "actual": {"eps": 0.62}}])
    assert s["count"] == 1 and s["by_surprise"]


# ── 결정적 + 중복원장/엔진 없음 + 안전 ──
def test_deterministic():
    a = analyze_headline("TSMC supplier expands", entity="TSMC")
    b = analyze_headline("TSMC supplier expands", entity="TSMC")
    assert a["event_type"] == b["event_type"] and a["affected_companies"] == b["affected_companies"]


def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


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
