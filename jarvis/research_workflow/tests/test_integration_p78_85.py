"""P78-85 통합/시각화 오케스트레이션 테스트 — 타임라인·그래프·건강·교차·품질·지속학습·콕핏.

핵심: 모두 기존 원장/엔진 재사용(읽기 전용, 지속학습만 rmi_ write) · 새 원장/엔진 없음 · 결정적.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_assistant import ledger as al
from jarvis.research_ingestion import ledger as ringl
from jarvis.research_ingestion.engine import ResearchIngestionEngine
from jarvis.research_memory_intelligence import ledger as ml
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow.cockpit import build_cockpit
from jarvis.research_workflow.continuous_learning import learning_status, on_research_complete
from jarvis.research_workflow.cross_strategy import compare, compare_all
from jarvis.research_workflow.health_monitor import build_health
from jarvis.research_workflow.knowledge_graph import REL_KINDS, build_knowledge_graph
from jarvis.research_workflow.quality_score import score_research
from jarvis.research_workflow.timeline import STAGE_ORDER, build_timeline

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

_FULL = {"return": 0.14, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}
_FAIL = {**_FULL, "sharpe": -0.2, "out_of_sample": -0.5, "cost_impact": 0.4, "max_drawdown": -0.4}


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """모든 관련 원장을 tmp _state 로 격리하고 실데이터 시드(성공 1·실패 1)."""
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda n: str(state / n)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    for lg in (ringl, ml, al, wl, el):
        monkeypatch.setattr(lg, "state_path", sp)
    eng = ResearchIngestionEngine()
    eng.ingest({"strategy_name": "momentum", "strategy_version": "v1", "hypothesis": "mom",
                "universe": "KR", "features": ["ret_12m"], "entry_rules": "top decile",
                "metrics": dict(_FULL), "source": "backtest_runner"}, NOW, commit=True)
    eng.ingest({"strategy_name": "orb", "strategy_version": "v1", "universe": "US",
                "metrics": dict(_FAIL), "source": "backtest_runner",
                "root_cause": "regime change"}, NOW, commit=True)
    return state


# ── P78 Timeline ──
def test_timeline_reconstructed(seeded):
    tl = build_timeline()
    assert tl["count"] >= 2                       # 시드 기록에서 재구성
    stages = {e["stage"] for e in tl["entries"]}
    assert stages & set(STAGE_ORDER)
    assert tl["is_decision"] is False


def test_timeline_topic_filter(seeded):
    tl = build_timeline("momentum")
    assert all("momentum" in (e["label"] + e["ref"]).lower() or e["source"] for e in tl["entries"])
    assert tl["count"] >= 1


def test_timeline_deterministic(seeded):
    assert build_timeline()["entries"] == build_timeline()["entries"]


# ── P79 Knowledge Graph ──
def test_graph_multi_entity(seeded):
    g = build_knowledge_graph()
    assert g["node_count"] > 0 and g["edge_count"] > 0
    assert "Strategy" in g["node_types"]          # ring_ 파생
    assert set(g["edge_kinds"]) <= set(REL_KINDS)


def test_graph_has_relationship_kinds(seeded):
    g = build_knowledge_graph()
    assert "uses" in g["edge_kinds"] or "failed" in g["edge_kinds"]


def test_graph_deterministic(seeded):
    assert build_knowledge_graph()["nodes"] == build_knowledge_graph()["nodes"]


# ── P81 Health ──
def test_health_metrics(seeded):
    h = build_health()
    assert 0 <= h["overall_health_score"] <= 100
    assert h["health_band"] in ("HEALTHY", "FAIR", "ATTENTION")
    assert h["knowledge_growth"] >= 1
    assert "validation" in h["coverage"]


def test_health_deterministic(seeded):
    assert build_health()["overall_health_score"] == build_health()["overall_health_score"]


# ── P83 Cross Strategy ──
def test_cross_strategy_compare():
    r = compare({"name": "Momentum", "returns": [1, 2, 3, 4], "metrics": {"sharpe": 0.9}},
                {"name": "Value", "returns": [4, 3, 2, 1], "metrics": {"sharpe": 0.5}})
    assert r["correlation"] == -1.0
    assert r["conflict"] is True
    assert 0 <= r["similarity"] <= 1
    assert r["is_decision"] is False


def test_cross_strategy_deterministic():
    a = {"name": "A", "returns": [1, 2, 3]}
    b = {"name": "B", "returns": [1, 2, 3]}
    assert compare(a, b) == compare(a, b)


def test_compare_all_matrix():
    m = compare_all([{"name": "A", "returns": [1, 2, 3]}, {"name": "B", "returns": [3, 2, 1]},
                     {"name": "C", "returns": [1, 1, 2]}])
    assert m["count"] == 3                         # 3C2


# ── P84 Quality ──
def test_quality_dimensions():
    qs = score_research({"strategy_name": "momentum", "hypothesis": "h", "entry_rules": "r",
                         "universe": "KR", "source": "bt", "metrics": dict(_FULL)})
    for d in ("reproducibility", "walk_forward", "random_baseline", "out_of_sample",
              "transaction_cost", "liquidity", "failure_learning", "portfolio_impact",
              "paper_performance", "evidence", "documentation", "confidence"):
        assert d in qs["dimensions"], d
    assert 0 <= qs["overall_quality"] <= 100
    assert qs["grade"] in ("A", "B", "C", "D")


def test_quality_deterministic():
    bt = {"strategy_name": "x", "metrics": dict(_FULL), "source": "bt"}
    assert score_research(bt) == score_research(bt)


def test_quality_incomplete_lower():
    hi = score_research({"strategy_name": "x", "source": "bt", "metrics": dict(_FULL)})
    lo = score_research({"strategy_name": "x", "source": "bt", "metrics": {"sharpe": 0.5}})
    assert hi["overall_quality"] > lo["overall_quality"]


# ── P82 Continuous Learning ──
def test_continuous_learning_updates_memory(seeded):
    res = on_research_complete({"strategy_name": "vwap", "universe": "KR", "metrics": dict(_FAIL),
                                "root_cause": "cost sensitivity"}, now=NOW, commit=True)
    assert "ingestion" in res["channels_touched"]
    assert "risk" in res["channels_touched"]
    # 메모리 갱신 확인
    assert len(ml.read_lessons()) >= 1


def test_learning_status(seeded):
    ls = learning_status()
    assert ls["total"] >= 1
    assert "lessons" in ls["channels"]


# ── P85 Cockpit ──
def test_cockpit_aggregates(seeded):
    c = build_cockpit()
    for k in ("research", "current_loop", "top_opportunities", "highest_risks",
              "portfolio_exposure", "research_health", "knowledge_growth", "timeline",
              "knowledge_graph", "research_queue", "human_review_queue", "recent_sessions",
              "quick_resume", "health_score"):
        assert k in c, k
    assert c["is_decision"] is False


# ── 중복 원장/엔진 없음(문서 규칙) ──
def test_no_new_ledger():
    # P78-85 는 원장을 추가하지 않는다(rwf_ 는 P64/P72 의 3개 그대로)
    assert wl.ALL_LEDGERS == (("rwf_runs.jsonl", "event_id"), ("rwf_sessions.jsonl", "event_id"),
                              ("rwf_loops.jsonl", "event_id"))


def test_no_new_engine_classes():
    # 통합/시각화 모듈은 execute/trade 등을 노출하지 않는다
    for f in ("timeline.py", "knowledge_graph.py", "health_monitor.py", "cross_strategy.py",
              "quality_score.py", "continuous_learning.py", "cockpit.py"):
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
