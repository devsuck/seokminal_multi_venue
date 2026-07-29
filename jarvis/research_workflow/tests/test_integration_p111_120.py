"""P111-120 라이브 데이터 인프라 테스트 — provider layer·pipelines·feed·data quality·live intel·ops validation.

핵심: External Data → Provider → Normalization → Event Intelligence → Research Trigger → Workflow → Memory.
모두 기존 벤더 클라이언트/어댑터 재사용 · 새 provider/DB/원장 없음 · 결정적 · 거래·집행·주문 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import data_quality as dq
from jarvis.research_workflow import fundamental_pipeline as fp
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import live_intelligence as li
from jarvis.research_workflow import market_pipeline as mp
from jarvis.research_workflow import news_pipeline as npx
from jarvis.research_workflow import operational_validation as ov
from jarvis.research_workflow import ownership_pipeline as op
from jarvis.research_workflow import providers as prov
from jarvis.research_workflow import research_feed as rf

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("providers.py", "market_pipeline.py", "news_pipeline.py", "fundamental_pipeline.py",
            "ownership_pipeline.py", "research_feed.py", "data_quality.py", "live_intelligence.py",
            "operational_validation.py")


# ── P111/P112 Provider layer ──
def test_provider_registry_catalog():
    r = prov.provider_registry()
    assert r["count"] >= 15 and r["available_count"] >= 1
    assert set(r["interface"]) == {"fetch", "normalize", "validate", "health_check"}
    cats = {p["category"] for p in r["providers"]}
    assert {"market", "news", "fundamental", "insider", "macro"} <= cats
    assert r["is_decision"] is False


def test_provider_interface_and_health():
    p = prov.provider_for("market")
    assert p.consumer == "market_data_adapter"
    h = p.health_check()
    assert set(h) >= {"provider", "available", "status", "consumer"}
    norm = p.normalize({"asset": "AAPL", "return": 0.08})
    assert p.validate(norm)["ok"] is True


def test_provider_normalize_routes_to_existing_adapters():
    assert prov.provider_for("news").normalize({"text": "beats earnings", "entity": "X"})["event_type"]
    assert prov.provider_for("insider").normalize(
        {"entity": "NVDA", "type": "BUY", "role": "CEO", "prior_return": -0.2})["is_trade_signal"] is False


# ── P113 Market pipeline ──
def test_market_pipeline_preserves_metadata():
    r = mp.run([{"asset": "AAPL", "open": 100, "close": 108, "timestamp": "2026-01-03T09:30:00Z",
                 "source": "yfinance"}], source="yfinance")
    assert r["count"] == 1 and r["market_events"][0]["event_type"] == "PRICE_SURGE"
    assert r["market_events"][0]["timestamp"] == "2026-01-03T09:30:00Z"
    assert r["raw_payload_metadata"][0]["source"] == "yfinance"
    assert "OHLCV" in r["supported"]


# ── P114 News pipeline ──
def test_news_pipeline_extracts_context_no_sentiment_score():
    r = npx.run([{"text": "TSMC supplier expands production capacity", "entity": "TSMC"}])
    c = r["research_context"][0]
    assert c["event_type"] == "SUPPLY_CHAIN_CHANGE" and c["importance"] in ("LOW", "MEDIUM", "HIGH")
    assert set(r["extracts"]) == {"company", "sector", "event_type", "importance", "historical_similarity"}
    assert "sentiment_score" not in c


# ── P115 Fundamental pipeline ──
def test_fundamental_pipeline_research_candidate():
    r = fp.run([{"company": "NVDA", "period": "2025Q4",
                 "expected": {"eps": 0.5}, "actual": {"eps": 0.62}}])
    assert r["count"] == 1 and r["research_candidates"][0]["overall_surprise"] == "POSITIVE_SURPRISE"
    assert r["research_candidates"][0]["is_research_candidate"] is True
    assert set(r["supported_metrics"]) >= {"revenue", "eps", "margin", "cashflow", "debt", "growth"}


# ── P116 Ownership pipeline ──
def test_ownership_pipeline_event_fields_not_signal():
    r = op.run([{"entity": "NVDA", "type": "BUY", "role": "CEO", "prior_return": -0.2,
                 "size": 2e6, "source": "SEC_FORM4", "actor": "CEO", "date": "2026-01-02"}])
    e = r["ownership_events"][0]
    for f in ("company", "actor", "transaction", "size", "date", "historical_context"):
        assert f in e, f
    assert e["is_trade_signal"] is False and e["is_research_trigger"] is True


# ── P117 Research feed ──
def test_research_feed_dedup_and_queue():
    r = rf.collect({"market": [{"asset": "AAPL", "return": 0.08, "source": "US"},
                               {"asset": "AAPL", "return": 0.08, "source": "US"}]})
    assert r["dropped_duplicates"] >= 1 and r["collected_count"] == 1
    assert "opportunity_queue" in r and r["is_decision"] is False
    assert r["schedule"]["auto_execution"] is False


def test_research_feed_health_and_retry_config():
    p = rf.ResearchFeedPipeline(interval_seconds=600, max_retries=3)
    s = p.schedule()
    assert s["interval_seconds"] == 600 and s["max_retries"] == 3


# ── P118 Data quality ──
def test_data_health_report():
    h = dq.build_data_health()
    assert h["overall_status"] in ("HEALTHY", "DEGRADED", "LIMITED")
    assert set(h["checks"]) == {"api_availability", "data_freshness", "schema_changes",
                                "missing_values", "abnormal_values"}
    assert "available" in h["api_availability"] and h["is_decision"] is False


def test_data_health_freshness_uses_existing_quality():
    h = dq.build_data_health({"AAPL": [{"symbol": "AAPL", "timestamp": "2020-01-01", "close": 100}]},
                             now="2026-01-01T00:00:00Z")
    assert h["freshness_and_values"] and "checks" in h["freshness_and_values"][0]


# ── P119 Live intelligence ──
def test_live_intelligence_sections():
    x = li.build_live_intelligence(demo=True)
    assert set(x) >= {"data_sources", "market_feed", "research_queue", "data_health"}
    assert x["data_sources"]["count"] >= 15 and x["is_decision"] is False


# ── P120 Operational validation ──
def test_operational_validation_full_chain():
    r = ov.validate_operations()
    names = {c["check"] for c in r["checks"]}
    assert names == {"data_ingestion_works", "duplicate_events_prevented",
                     "research_candidates_generated", "dashboard_displays_updates",
                     "existing_ledgers_unchanged"}
    assert r["operational"] is True and r["architecture_safety"]["safe"] is True


def test_architecture_safety_no_new_ledger():
    s = ov.architecture_safety()
    assert s["safe"] is True and s["no_new_ledger"] is True and s["violations"] == []


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = mp.run([{"asset": "X", "return": 0.08}])
    b = mp.run([{"asset": "X", "return": 0.08}])
    assert a["market_events"] == b["market_events"]


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
