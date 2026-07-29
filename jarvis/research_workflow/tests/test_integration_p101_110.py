"""P101-110 연구 검증 루프 테스트 — 트리거·백테스트브리지·페이퍼검증·격차·생애주기·품질·운영이벤트·감사·릴리스.

핵심: Market Event → Trigger → Hypothesis → Experiment → Backtest → Paper → Validation → Risk → Memory.
모두 기존 엔진(event_stream/opportunity/planner/forward_testing/quality_score/timeline) 재사용 ·
새 원장/엔진/DB 없음 · 결정적 · 거래·집행·신호 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import backtest_bridge as bb
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import ops_events as oe
from jarvis.research_workflow import paper_validation as pv
from jarvis.research_workflow import quality_monitor as qm
from jarvis.research_workflow import research_audit as ra
from jarvis.research_workflow import research_trigger as rt
from jarvis.research_workflow import strategy_lifecycle as sl
from jarvis.research_workflow import validation_gap as vg
from jarvis.research_workflow.release_validation import safety_check, validate_release

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("research_trigger.py", "backtest_bridge.py", "paper_validation.py", "validation_gap.py",
            "strategy_lifecycle.py", "quality_monitor.py", "ops_events.py", "research_audit.py",
            "release_validation.py")

_BT = {"strategy_name": "tsmom", "universe": "US", "hypothesis": "trend", "entry_rules": "x",
       "source": "t", "metrics": {"return": 0.2, "sharpe": 1.4, "max_drawdown": -0.1,
       "walk_forward": 0.6, "out_of_sample": 0.5, "cost_impact": 0.02, "random_baseline": 0.1,
       "turnover": 0.3, "parameter_stability": 0.7, "n_obs": 800, "volatility": 0.14}}
_PAPER = {"strategy_name": "tsmom", "regime": "HIGH_VOL",
          "metrics": {"return": 0.05, "sharpe": 0.4, "max_drawdown": -0.18, "cost_impact": 0.09,
                      "turnover": 0.6, "volatility": 0.22}}


# ── P101 Research Trigger ──
def test_trigger_from_event_is_research_task_not_signal():
    t = rt.from_event({"kind": "earnings", "entity": "NVDA", "text": "NVDA earnings beat"})
    assert t.trigger_type == "earnings_reaction_study"
    assert t.is_research_task is True and t.is_trade_signal is False
    assert set(t.to_dict()) >= {"event_id", "trigger_type", "related_assets", "affected_sector",
                                "historical_context", "suggested_research_area", "confidence"}


def test_trigger_dispatch_chains_opportunity_and_hypothesis():
    d = rt.dispatch({"kind": "supply", "entity": "TSMC", "text": "TSMC supply disruption"})
    assert d["is_trade_signal"] is False and d["is_decision"] is False
    assert "opportunity_candidates" in d and "suggested_hypotheses" in d


# ── P102 Backtest Bridge ──
def test_backtest_job_lifecycle_no_auto_execution():
    job = bb.create_job({"statement": "tsmom produces trend edge"})
    assert job.status == bb.S_CREATED and job.strategy == "tsmom"
    assert bb.submit_for_human_run(job).status == bb.S_WAITING_HUMAN
    assert bb.mark_running(bb.submit_for_human_run(job)).status == bb.S_EXTERNAL_RUNNING
    comp = bb.complete_job(job, _BT)
    assert comp["job"]["status"] in (bb.S_COMPLETED, bb.S_FAILED)
    assert comp["is_decision"] is False


# ── P103 Paper Validation ──
def test_paper_validation_detects_backtest_success_paper_failure():
    r = pv.validate(_BT, _PAPER)
    assert r["backtest_success"] is True and r["paper_failure"] is True
    assert r["status"] == "BACKTEST_SUCCESS_PAPER_FAILURE"
    for k in ("return", "volatility", "drawdown", "turnover", "exposure", "benchmark_difference"):
        assert k in r["tracked_metrics"], k
    assert r["is_decision"] is False


# ── P104 Validation Gap ──
def test_validation_gap_five_dimensions_and_causes():
    g = vg.analyze_gap(_BT, _PAPER)
    assert set(g["gaps"]) == {"performance", "risk", "cost", "regime", "behavior"}
    assert g["possible_causes"] and all("cause" in c for c in g["possible_causes"])
    assert g["is_advisory"] is True and g["is_decision"] is False


# ── P105 Strategy Lifecycle ──
def test_lifecycle_states_and_board():
    assert sl.LIFECYCLE == ("DISCOVERED", "HYPOTHESIS", "EXPERIMENT", "BACKTEST", "PAPER",
                            "REVIEW", "ARCHIVED")
    st = sl.lifecycle_state("tsmom")
    assert st["current_state"] in sl.LIFECYCLE
    b = sl.board(strategies=["tsmom", "momentum"])
    assert b["count"] == 2 and list(b["lifecycle"]) == list(sl.LIFECYCLE)


# ── P106 Quality Monitor ──
def test_quality_monitor_core_dimensions_and_gate():
    q = qm.evaluate(_BT)
    for k in ("sample_size", "out_of_sample", "walk_forward", "cost_sensitivity",
              "parameter_stability", "reproducibility"):
        assert k in q["core_dimensions"], k
    assert q["gate"] in ("ACCEPT", "NEEDS_MORE_EVIDENCE")
    assert isinstance(q["quality_score"], (int, float)) and q["is_decision"] is False


# ── P107 Ops Events ──
def test_ops_events_types_and_readonly():
    ev = oe.ops_events()
    assert set(ev["event_types"]) == {"NEW_HYPOTHESIS", "BACKTEST_COMPLETED", "VALIDATION_FAILED",
                                      "PAPER_DIVERGENCE", "HUMAN_REVIEW_REQUIRED"}
    assert isinstance(ev["events"], list) and ev["is_decision"] is False


# ── P109 Audit ──
def test_audit_sections_reconstructed():
    a = ra.audit_strategy("tsmom")
    for sec in ("origin_event", "hypothesis", "experiments", "backtests", "failures", "lessons"):
        assert sec in a["sections"], sec
    assert "completeness" in a and a["is_decision"] is False
    assert "strategies" in ra.audit_coverage()


# ── P110 Release Validation + Safety ──
def test_release_validation_full_loop():
    rel = validate_release()
    stages = [s["stage"] for s in rel["loop_steps"]]
    assert stages[0].startswith("Market Event") and "Memory" in stages[-1]
    assert rel["loop_complete"] is True
    assert rel["safety"]["safe"] is True and rel["release_ready"] is True


def test_safety_check_no_forbidden():
    s = safety_check()
    assert s["safe"] is True and s["violations"] == []


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = pv.validate(_BT, _PAPER)
    b = pv.validate(_BT, _PAPER)
    assert a["status"] == b["status"] and a["tracked_metrics"] == b["tracked_metrics"]


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
