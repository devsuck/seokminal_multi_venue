"""P171-180 자율 연구 지능 강화 테스트 — creative hypothesis·search·queue·prioritization·expansion·
reflection·planning·collaboration·productivity·autonomy validation.

핵심: 기존 엔진 조율만 · 새 패키지/엔진/원장/DB 없음 · 자문 전용 · 결정적 · 자율 승인 없음 ·
거래·집행·자본배분 없음 · 연구 자동 실행 없음 · 사람이 모든 결정. **아키텍처 동결 유지.**
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import autonomy_validation as av
from jarvis.research_workflow import collaborative_research as cr
from jarvis.research_workflow import continuous_queue as cq
from jarvis.research_workflow import creative_hypothesis as ch
from jarvis.research_workflow import experiment_prioritization as ep
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import productivity_optimization as po
from jarvis.research_workflow import research_expansion as rx
from jarvis.research_workflow import research_planning as rp
from jarvis.research_workflow import research_search as rs
from jarvis.research_workflow import self_reflection as sr

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("creative_hypothesis.py", "research_search.py", "continuous_queue.py",
            "experiment_prioritization.py", "research_expansion.py", "self_reflection.py",
            "research_planning.py", "collaborative_research.py", "productivity_optimization.py",
            "autonomy_validation.py")


# ── P171 Creative Hypothesis ──
def test_creative_hypothesis_multi_source_enriched():
    r = ch.discover_hypotheses("momentum KR equities", limit=8)
    assert r["hypothesis_count"] >= 1 and r["is_decision"] is False
    h = r["hypotheses"][0]
    for f in ("novelty_score", "evidence_chain", "similar_historical_research",
              "conflicting_evidence", "uncertainty", "confidence", "required_validation"):
        assert f in h, f
    # 다양성 — 2개 이상의 소스
    assert len(r["diversity"]["sources"]) >= 2


def test_creative_hypothesis_deterministic():
    a = ch.discover_hypotheses("momentum", limit=6)["hypotheses"]
    b = ch.discover_hypotheses("momentum", limit=6)["hypotheses"]
    assert [x["hypothesis_id"] for x in a] == [x["hypothesis_id"] for x in b]


# ── P172 Research Search ──
def test_research_search_tree_prune_merge():
    r = rs.build_search_space("momentum produces a cost-robust edge", top_k=10)
    assert r["tree"] and r["is_decision"] is False
    assert "highest_value_candidates" in r and r["surfaced_count"] <= 10
    # 스코어 내림차순
    scores = [c["score"] for c in r["highest_value_candidates"]]
    assert scores == sorted(scores, reverse=True)


# ── P173 Continuous Queue ──
def test_continuous_queue_multi_source():
    r = cq.build_continuous_queue(topic="momentum")
    assert "backlog" in r and r["is_decision"] is False
    assert isinstance(r["by_source"], dict)


# ── P174 Experiment Prioritization ──
def test_experiment_prioritization_extra_factors():
    r = ep.prioritize_experiments(topic="momentum", limit=5)
    assert r["is_decision"] is False
    for f in ("validation_complexity", "research_coverage", "knowledge_gap"):
        assert f in r["ranking_factors"], f
    if r["recommendations"]:
        assert "composite_score" in r["recommendations"][0]


# ── P175 Research Expansion ──
def test_research_expansion_hierarchical_no_bruteforce():
    r = rx.expand_research("momentum edge", top_k=20)
    assert r["is_decision"] is False and "hierarchical" in r["expansion_strategy"]
    assert r["depth_breakdown"]["level_2"] >= 0
    assert r["surfaced_count"] <= 20


# ── P176 Self Reflection ──
def test_self_reflection_seven_questions():
    r = sr.reflect_on_cycle({"outcome": "FAILURE",
                             "backtest": {"metrics": {"sharpe": -0.3, "walk_forward": 0.1,
                                                      "out_of_sample": -0.2}}})
    for q in ("assumptions_failed", "assumptions_survived", "surprises", "missing_evidence",
              "strengthened_evidence", "test_next", "never_test_again"):
        assert q in r["reflection"], q
    assert r["is_decision"] is False
    # 미커밋 시 메모리 미기록
    assert r["lessons_stored_via"] == "none"


# ── P177 Research Planning ──
def test_research_planning_all_horizons():
    r = rp.build_research_plan(topic="momentum")
    for h in ("daily", "weekly", "monthly", "quarterly"):
        assert h in r["plans"], h
    assert r["plans"]["quarterly"]["roadmap"] and r["is_decision"] is False


# ── P178 Collaborative Research ──
def test_collaborative_actions_no_autonomous_approval():
    r = cr.run_collaborative_research("Does momentum work?", hypothesis="momentum and reversal combine")
    assert r["director_synthesis"]["autonomous_approval"] is False
    assert r["is_decision"] is False
    valid = {"challenge", "refine", "split", "merge", "reject", "request_evidence"}
    assert all(a["action"] in valid for a in r["collaboration_actions"])
    # 복합 가설 → split 포함
    assert "split" in r["action_counts"]


# ── P179 Productivity ──
def test_productivity_eight_metrics_recommend_only():
    r = po.build_productivity_report()
    for k in ("research_throughput", "duplicate_reduction", "knowledge_growth", "learning_speed",
              "research_quality", "validation_quality", "evidence_coverage",
              "false_positive_reduction"):
        assert k in r["metrics"], k
    assert r["recommendations"] and r["is_decision"] is False


# ── P180 Autonomy Validation ──
def test_autonomy_validation_passes():
    v = av.validate_autonomy()
    assert v["validated"] is True
    assert v["duplicated_logic"] == []
    assert v["reuse_analysis"]["reuse_count"] >= 10
    names = {c["check"] for c in v["checks"]}
    for c in ("no_execution_engine", "no_broker_imports", "no_trade_functions",
              "no_capital_allocation", "no_autonomous_approval", "no_new_ledger",
              "no_duplicated_logic", "existing_architecture_reused", "advisory_only"):
        assert c in names, c


# ── 새 원장 없음 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


# ── 금지 def/import/모델 누출 없음(직접 스캔) ──
def test_no_forbidden_defs_imports_leak():
    for f in _MODULES:
        src = open(SRC / f).read()
        assert MODEL_LEAK_TOKEN not in src.lower(), f
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in
                               ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                                "jarvis.live_trading", "jarvis.portfolio_execution")), (f, node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                         "place_order", "deploy_strategy"), (f, node.name)
