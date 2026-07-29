"""P131-140 연구 지식 지능 계층 테스트 — memory audit·kg upgrade·recall·similarity·conflict·learning·agent memory·quality·brain.

핵심: 질문 → 회수 → 에이전트 분석 → 충돌검사 → 결과 → 교훈. 모두 기존 rmi_/graph/recall 재사용 ·
새 DB/원장/메모리/벡터DB 없음 · 결정적 · 거래·집행 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import agent_memory as am
from jarvis.research_workflow import brain_validation as bv
from jarvis.research_workflow import conflict_detection as cd
from jarvis.research_workflow import knowledge_graph_upgrade as kg
from jarvis.research_workflow import knowledge_quality as kq
from jarvis.research_workflow import learning_engine as le
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import memory_audit as ma
from jarvis.research_workflow import research_similarity as rs
from jarvis.research_workflow import semantic_recall as sr

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("memory_audit.py", "knowledge_graph_upgrade.py", "semantic_recall.py",
            "research_similarity.py", "conflict_detection.py", "learning_engine.py",
            "agent_memory.py", "knowledge_quality.py", "brain_validation.py")


# ── P131 Memory audit ──
def test_memory_audit_entities_and_gaps():
    a = ma.audit_memory()
    assert set(a["entity_types"]) == {"Experiment", "Failure", "Lesson", "Success", "Strategy",
                                      "Company", "Market Event"}
    assert len(a["memory_stores"]) >= 6 and a["missing_connections"]
    assert a["is_decision"] is False


# ── P132 Knowledge graph upgrade ──
def test_knowledge_graph_research_chain():
    g = kg.build_research_knowledge_graph()
    assert g["research_chain"] == ["Research Question", "Hypothesis", "Experiment", "Result",
                                   "Failure/Success", "Lesson"]
    assert "similar_research" in g["chain_kinds"] and "base_graph" in g
    assert g["is_decision"] is False


# ── P133 Semantic recall ──
def test_semantic_recall_context_package():
    p = sr.recall_context("Does momentum work in the current regime?")
    for f in ("relevant_experiments", "similar_failures", "past_conclusions", "contradicting_evidence"):
        assert f in p, f
    assert p["is_context_package"] is True and p["is_decision"] is False


# ── P134 Similarity ──
def test_similarity_no_embeddings_deterministic():
    a = rs.compare("Does momentum work in high vol?", "Does momentum work in trending market?")
    b = rs.compare("Does momentum work in high vol?", "Does momentum work in trending market?")
    assert a["similarity_score"] == b["similarity_score"] and "momentum" in a["shared_tokens"]
    r = rs.ResearchSimilarity().rank("momentum", ["momentum trend", "mean reversion"])
    assert r["ranked"][0]["similarity_score"] >= r["ranked"][-1]["similarity_score"]


def test_similarity_features():
    a = rs.compare({"statement": "x", "feature_set": ["mom_12_1"], "universe": "US"},
                   {"statement": "y", "feature_set": ["mom_12_1"], "universe": "US"}, kind="experiment")
    assert a["feature_similarity"] is not None and a["feature_similarity"] > 0


# ── P135 Conflict detection ──
def test_conflict_detection_shape():
    c = cd.detect_conflicts()
    assert "conflicts" in c and "checked" in c and c["is_decision"] is False


# ── P136 Learning engine ──
def test_learning_engine_lesson_structure_stores_rmi():
    l = le.learn(backtest={"strategy_name": "tsmom", "metrics": {"return": 0.2, "sharpe": 1.4}},
                 outcome="SUCCESS")
    for f in ("what_happened", "why", "when_applicable", "when_invalid"):
        assert f in l["lesson"], f
    assert l["stored"].get("ledger") == "rmi_lessons" and l["committed"] is False


# ── P137 Agent memory ──
def test_agent_memory_before_during_after_no_direct_writes():
    ki = am.knowledge_informed_research("Does momentum work?")
    assert ki["before"]["previous_knowledge"] and len(ki["during"]["pipeline"]) == 5
    assert ki["after"]["final_lesson"] and ki["direct_ledger_writes"] is False
    assert ki["is_decision"] is False


# ── P139 Knowledge quality ──
def test_knowledge_health_checks():
    h = kq.build_knowledge_health()
    assert set(h["checks"]) == {"duplicate_lessons", "outdated_knowledge", "contradictions",
                                "missing_evidence"}
    assert h["grade"] in ("HEALTHY", "FAIR", "DEGRADED", "EMPTY") and h["is_decision"] is False


# ── P140 Brain validation ──
def test_brain_validation_full_chain():
    v = bv.validate_brain()
    names = {c["check"] for c in v["checks"]}
    assert names == {"past_research_retrieved", "failures_reused", "no_duplicate_memory",
                     "agents_use_knowledge", "dashboard_displays_knowledge"}
    assert v["validated"] is True and v["safety"]["safe"] is True


def test_brain_safety_no_new_ledger():
    s = bv.brain_safety()
    assert s["safe"] is True and s["no_new_ledger"] is True and s["violations"] == []


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = kg.build_research_knowledge_graph()
    b = kg.build_research_knowledge_graph()
    assert a["node_count"] == b["node_count"] and a["edge_kinds"] == b["edge_kinds"]


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
