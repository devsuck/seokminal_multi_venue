"""Market Event Intelligence 테스트 — 공급망 전파·영향체인·후보생성·확장·안전.

핵심(문서 §Tests #7): 이벤트 분석이 공급망 관계를 연결한다 —
Taiwan earthquake → TSMC → NVIDIA → Semiconductor ETF.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_assistant.event_intelligence import (
    HIGH,
    MarketEventIntelligence,
)

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


def test_taiwan_earthquake_supply_chain():
    imp = MarketEventIntelligence().analyze_event("Taiwan earthquake")
    assert imp.origin == "Taiwan"
    # Taiwan → TSMC → NVIDIA → SOXX/SMH(반도체 ETF)
    assert "TSMC" in imp.affected_entities
    assert "NVIDIA" in imp.affected_entities
    assert any(e in imp.affected_entities for e in ("SOXX", "SMH"))


def test_impact_chain_edges():
    imp = MarketEventIntelligence().analyze_event("Taiwan earthquake")
    edges = {(e["source"], e["target"]) for e in imp.impact_chain["edges"]}
    assert ("Taiwan", "TSMC") in edges
    assert ("TSMC", "NVIDIA") in edges


def test_event_dict_explicit_origin():
    imp = MarketEventIntelligence().analyze_event({"origin": "TSMC", "text": "fab outage"})
    assert imp.origin == "TSMC"
    assert "NVIDIA" in imp.affected_entities


def test_generate_candidates_for_queue():
    cands = MarketEventIntelligence().generate_candidates("Taiwan earthquake")
    assert cands
    # 큐가 소비하는 형태(name/entity/reason/confidence)
    assert all({"name", "entity", "reason", "confidence"} <= set(c) for c in cands)
    nvidia = [c for c in cands if c["entity"] == "NVIDIA"]
    assert nvidia


def test_confidence_by_distance():
    imp = MarketEventIntelligence().analyze_event("Taiwan earthquake")
    tsmc = next(c for c in imp.candidates if c.entity == "TSMC")
    assert tsmc.confidence == HIGH   # 직접 연결(거리 1)


def test_unknown_event_no_origin():
    imp = MarketEventIntelligence().analyze_event("random unrelated headline")
    assert imp.origin == ""
    assert imp.affected_entities == []


def test_add_relationship_extends_graph():
    mei = MarketEventIntelligence()
    mei.add_relationship("KoreaQuake", "Samsung", "hosts")
    mei.add_relationship("Samsung", "SOXX", "etf_member")
    imp = mei.analyze_event("KoreaQuake disaster")
    assert "Samsung" in imp.affected_entities


def test_relationship_graph_view():
    g = MarketEventIntelligence().relationship_graph()
    assert g["node_count"] > 0 and g["edge_count"] > 0
    labels = {n["id"] for n in g["nodes"]}
    assert "TSMC" in labels and "NVIDIA" in labels


def test_advisory():
    imp = MarketEventIntelligence().analyze_event("Taiwan earthquake")
    d = imp.to_dict()
    assert d["is_advisory"] is True and d["is_decision"] is False
    assert d["requires_human_review"] is True


def test_deterministic():
    a = MarketEventIntelligence().analyze_event("Taiwan earthquake").to_dict()
    b = MarketEventIntelligence().analyze_event("Taiwan earthquake").to_dict()
    assert a["affected_entities"] == b["affected_entities"]


# ── 안전 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "event_intelligence.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "event_intelligence.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "event_intelligence.py").read().lower()
