"""P151-160 기관 인텔리전스 확장 테스트 — data production·sector·macro·company·context·cross-asset·memory·quality·validation.

핵심: 시장·섹터·매크로·기업·지식·품질을 하나의 연구 컨텍스트로. 모두 기존 엔진 재사용 ·
새 DB/원장/벡터DB/메모리/엔진 없음 · 자문 전용 · 결정적 · 거래·집행 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import company_intelligence as ci
from jarvis.research_workflow import cross_asset_intelligence as ca
from jarvis.research_workflow import data_production as dp
from jarvis.research_workflow import institutional_intelligence_validation as iv
from jarvis.research_workflow import institutional_memory_expansion as im
from jarvis.research_workflow import intelligence_quality as iq
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import macro_intelligence as mi
from jarvis.research_workflow import research_context_engine as rc
from jarvis.research_workflow import sector_intelligence as si

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("data_production.py", "sector_intelligence.py", "macro_intelligence.py",
            "company_intelligence.py", "research_context_engine.py", "cross_asset_intelligence.py",
            "institutional_memory_expansion.py", "intelligence_quality.py",
            "institutional_intelligence_validation.py")


# ── P151 Data production ──
def test_data_production_report_fields_no_mutation():
    d = dp.build_data_production()
    assert d["count"] >= 15 and d["reports"]
    r0 = d["reports"][0]
    for f in ("provider", "source", "availability", "freshness", "quality_score", "failure_reason", "lineage"):
        assert f in r0, f
    assert d["overall_status"] in ("HEALTHY", "DEGRADED", "LIMITED") and d["is_decision"] is False


# ── P152 Sector ──
def test_sector_intelligence_no_ranking():
    s = si.analyze_sector("semiconductor")
    for f in ("sector", "key_entities", "events", "historical_context", "risk_factors", "research_questions"):
        assert f in s, f
    assert s["key_entities"] and "investment_ranking" not in s and s["is_decision"] is False


# ── P153 Macro ──
def test_macro_context_no_forecast():
    m = mi.build_macro_context(indicators={"fed_funds": 5.0, "cpi": 3.5, "unemployment": 4.2})
    for f in ("macro_state", "indicators", "historical_similarity", "affected_assets", "uncertainty"):
        assert f in m, f
    assert m["macro_state"] in ("TIGHTENING", "EASING/RECESSION_RISK", "MID_CYCLE", "UNKNOWN")
    assert "forecast" not in m and m["is_decision"] is False


# ── P154 Company ──
def test_company_intelligence_no_signal():
    c = ci.analyze_company("TSMC")
    for f in ("entity", "relationships", "events", "financial_context", "historical_lessons", "risks"):
        assert f in c, f
    assert set(c["relationships"]) >= {"suppliers", "customers", "competitors"}
    assert c["is_trade_signal"] is False


# ── P155 Research context ──
def test_research_context_eight_sections():
    r = rc.build_research_context("Does momentum work in semiconductor?", sector="semiconductor", entity="TSMC")
    p = r["package"]
    assert len(p) == 8 and "1_question" in p and "8_missing_evidence" in p
    assert "7_contradictions" in p and r["is_context_package"] is True and r["is_decision"] is False


# ── P156 Cross asset ──
def test_cross_asset_no_allocation():
    x = ca.build_cross_asset(correlations={"AAPL~SPY": 0.72, "GLD~DXY": -0.58})
    assert x["asset_classes"] == ["Equity", "ETF", "Index", "Commodity", "FX", "Macro"]
    assert x["correlations"] and x["risk_transmission"] and "allocation" not in x
    assert x["is_decision"] is False


# ── P157 Memory expansion ──
def test_institutional_memory_no_new_storage():
    m = im.build_institutional_memory()
    for f in ("research_themes", "market_cycles", "successful_studies", "failed_studies", "totals"):
        assert f in m, f
    assert m["is_decision"] is False


# ── P158 Intelligence quality ──
def test_intelligence_quality_five_dimensions():
    q = iq.score_intelligence(topic="momentum")
    assert set(q["dimensions"]) == {"data_quality", "evidence_quality", "historical_relevance",
                                    "conflict_level", "uncertainty"}
    assert q["confidence"] in ("HIGH", "MEDIUM", "LOW") and q["is_decision"] is False


def test_intelligence_quality_single_source_low():
    q = iq.score_intelligence(topic="obscure_topic_xyz", n_sources=1)
    assert q["confidence"] == "LOW"


# ── P160 Validation ──
def test_intelligence_validation_seven_checks():
    v = iv.validate_intelligence()
    names = {c["check"] for c in v["checks"]}
    assert names == {"data_sources_connect", "sector_context_generated", "macro_context_generated",
                     "company_graph_works", "research_context_combines", "quality_scoring_works",
                     "no_duplicate_systems"}
    assert v["validated"] is True and v["safety"]["safe"] is True


def test_intelligence_safety_no_new_ledger():
    s = iv.intelligence_safety()
    assert s["safe"] is True and s["no_new_ledger"] is True and s["violations"] == []


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = mi.build_macro_context(indicators={"fed_funds": 5.0, "cpi": 3.5})
    b = mi.build_macro_context(indicators={"fed_funds": 5.0, "cpi": 3.5})
    assert a["macro_state"] == b["macro_state"] and a["affected_assets"] == b["affected_assets"]


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
