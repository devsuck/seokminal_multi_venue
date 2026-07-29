"""Research Factory 테스트 — 약한 아이디어 조기 REJECT 깔때기.

핵심: 각 게이트가 REJECT · LLM 은 economic rationale 심판 전용(생성 절대 아님) · 그 외 결정적 ·
BH-FDR 배치 게이트 · 살아남은 것만 Paper Candidate · 실행/배분/포트폴리오 없음 · 새 원장 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import research_factory as rf

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


# ── Gate 1: Economic rationale — LLM 은 심판 전용 ──
def test_economic_gate_rejects_without_rationale():
    g = rf.economic_rationale_gate({"thesis": "x", "rationale": ""})
    assert g["passed"] is False and "weak idea" in g["reason"]


def test_economic_gate_pending_without_judge():
    g = rf.economic_rationale_gate({"thesis": "x", "rationale": "mean reversion after liquidity shock"})
    assert g["passed"] is None and g["provisional"] is True   # 가짜 통과 없음


def test_economic_gate_llm_judge_rejects_and_passes():
    reject_judge = lambda ctx: {"convincing": False, "reason": "no mechanism"}  # noqa: E731
    pass_judge = lambda ctx: {"convincing": True, "mechanism": "risk premium", "reason": "ok"}  # noqa: E731
    assert rf.economic_rationale_gate({"thesis": "x", "rationale": "r"}, judge=reject_judge)["passed"] is False
    g = rf.economic_rationale_gate({"thesis": "x", "rationale": "r"}, judge=pass_judge)
    assert g["passed"] is True and g["judged_by"] == "llm"


# ── Gate 3: Similarity — 중복 REJECT ──
def test_similarity_gate_rejects_duplicate():
    idea = {"thesis": "momentum produces persistent cost-robust edge in KR"}
    g = rf.similarity_gate(idea, existing=["momentum produces persistent cost-robust edge in KR"])
    assert g["passed"] is False and g["max_similarity"] >= 0.85


# ── Gate 6-7: Backtest / Walk-forward REJECT ──
def test_backtest_gate_rejects_negative():
    assert rf.backtest_gate({"metrics": {"sharpe": -0.3}})["passed"] is False
    assert rf.backtest_gate({"metrics": {}})["passed"] is None   # 결과 없음 → 외부 대기(자동 아님)


def test_walk_forward_gate_rejects_oos_collapse():
    g = rf.walk_forward_gate({"metrics": {"wf_first": 0.5, "wf_second": -0.2}})
    assert g["passed"] is False and "overfit" in g["reason"]


# ── Gate 8: BH-FDR ──
def test_bh_fdr_deterministic():
    # p=0.001 생존, p=0.9 기각
    mask = rf._bh_fdr([0.001, 0.9, 0.02], alpha=0.1)
    assert mask[0] is True and mask[1] is False


# ── Gate 10: Slippage — 비용 민감 REJECT ──
def test_slippage_gate_rejects_cost_sensitive():
    assert rf.slippage_gate({"metrics": {"cost_impact": 0.5}})["passed"] is False
    assert rf.slippage_gate({"metrics": {"net_after_cost": -10}})["passed"] is False


# ── 전체 깔때기: judge 통과 + 강한 지표 → Paper Candidate ──
def test_full_funnel_survivor_reaches_paper_candidate():
    judge = lambda ctx: {"convincing": True, "mechanism": "risk premium", "reason": "ok"}  # noqa: E731
    strong = {"strategy_id": "strong_x", "thesis": "novel uncrowded edge zzz",
              "rationale": "documented risk premium", "data_category": "market",
              "metrics": {"sharpe": 0.8, "net": 100, "wf_first": 0.4, "wf_second": 0.3,
                          "empirical_p": 0.001, "cost_impact": 0.1, "capacity": 1.0}}
    weak = {"strategy_id": "weak_y", "thesis": "overfit thing",
            "rationale": "documented", "data_category": "market",
            "metrics": {"sharpe": 0.6, "wf_first": 0.5, "wf_second": -0.3, "empirical_p": 0.9}}
    r = rf.run_factory([strong, weak], judge=judge)
    assert "strong_x" in r["candidates"]
    assert r["paper_candidates"] >= 1 and r["rejected"] >= 1
    assert r["is_decision"] is False


# ── LLM 사용 규칙 명시 ──
def test_llm_usage_is_judge_only():
    r = rf.run_factory([], judge=None)
    assert "economic_rationale judge ONLY" in r["llm_usage"]
    assert "never idea generator" in r["llm_usage"]


# ── 게이트 순서(깔때기) ──
def test_gate_order():
    assert rf.GATES[0] == "economic_rationale" and rf.GATES[-1] == "paper_candidate"
    assert "multiple_testing" in rf.GATES and "walk_forward" in rf.GATES


# ── 새 원장 없음 + 금지 스캔 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


def test_no_forbidden_defs_imports_leak():
    src = open(SRC / "research_factory.py").read()
    assert MODEL_LEAK_TOKEN not in src.lower()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in
                           ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                            "jarvis.live_trading", "jarvis.portfolio_execution")), node.module
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                     "place_order", "deploy_strategy"), node.name
