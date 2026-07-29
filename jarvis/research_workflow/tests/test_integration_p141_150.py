"""P141-150 연구 운영 & 기관 배포 테스트 — scheduler·briefing·company·strategy health·report·workspace·outcome·agent perf·v1.5.

핵심: External Data → Opportunity → Agent Research → Experiment → Validation → Knowledge → Improvement.
모두 기존 엔진 재사용 · 새 DB/원장/메모리/실행엔진 없음 · 자문 전용 · 결정적 · 거래·집행 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import agent_performance as ap
from jarvis.research_workflow import company_monitor as cm
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import morning_briefing as mb
from jarvis.research_workflow import ops_validation as ov
from jarvis.research_workflow import report_automation as ra
from jarvis.research_workflow import research_outcome_tracker as ot
from jarvis.research_workflow import research_scheduler as rsch
from jarvis.research_workflow import research_workspace as rws
from jarvis.research_workflow import strategy_health as sh

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("research_scheduler.py", "morning_briefing.py", "company_monitor.py", "strategy_health.py",
            "report_automation.py", "research_workspace.py", "research_outcome_tracker.py",
            "agent_performance.py", "ops_validation.py")


# ── P141 Scheduler ──
def test_scheduler_operation_plan_no_auto():
    p = rsch.plan_cycle("daily")
    for f in ("cycle_type", "tasks", "assigned_agents", "status", "human_review_required"):
        assert f in p, f
    assert p["auto_execution"] is False and p["cycle_type"] == "daily"
    assert rsch.plan_cycle("weekly")["cycle_type"] == "weekly"


# ── P142 Briefing ──
def test_morning_briefing_six_sections():
    b = mb.generate(events=[{"kind": "macro", "text": "CPI surprise"}])
    assert len(b["brief"]) == 6 and "1_market_condition" in b["brief"]
    assert b["confidence"] in ("LOW", "MEDIUM", "HIGH") and b["limitations"]
    assert b["is_trade_signal"] is False


# ── P143 Company monitor ──
def test_company_monitor_report_no_signal():
    r = cm.update("NVDA", financials=[{"company": "NVDA", "expected": {"eps": 0.5}, "actual": {"eps": 0.62}}])
    for f in ("company", "events", "impact", "historical_context", "research_priority"):
        assert f in r, f
    assert r["research_priority"] in ("LOW", "MEDIUM", "HIGH") and r["is_trade_signal"] is False


# ── P144 Strategy health ──
def test_strategy_health_report_fields():
    h = sh.report("tsmom", metrics={"sharpe": 1.5, "out_of_sample": 0.5, "walk_forward": 0.6,
                                    "cost_impact": 0.02, "parameter_stability": 0.7})
    for f in ("strategy", "health_score", "warnings", "historical_context", "review_needed"):
        assert f in h, f
    assert isinstance(h["health_score"], (int, float)) and h["is_decision"] is False


# ── P145 Report automation ──
def test_report_automation_eight_sections():
    r = ra.generate("daily_report", "Does momentum work?", review={"verdict": "WARN"})
    secs = list(r["report"])
    assert len(secs) == 8 and secs[0] == "1_research_question" and secs[-1] == "8_next_research_step"
    assert "6_contradictions" in r["report"] and r["confidence"] in ("LOW", "MEDIUM", "HIGH")
    assert r["limitations"] and r["is_decision"] is False


# ── P146 Workspace ──
def test_workspace_actions_no_invest_approve():
    w = rws.build_workspace()
    assert set(w["available_actions"]) == {"review", "comment", "request_revision", "archive"}
    assert "approve_investment" in w["forbidden_actions"] and "execute_trade" in w["forbidden_actions"]
    act = rws.act("comment", "strategy:x", comment="needs walk-forward")
    assert act["is_binding"] is False and act["is_decision"] is False


def test_workspace_rejects_unknown_action():
    assert "error" in rws.act("approve", "x")


# ── P147 Outcome tracker ──
def test_outcome_tracker_accuracy_report():
    o = ot.track("AI semiconductor demand increases", expected={"revenue_growth": 0.2},
                 actual={"revenue_growth": 0.25}, period="2025Q4")
    for f in ("hypothesis", "expected_outcome", "actual_outcome", "time_period", "differences", "lesson"):
        assert f in o, f
    assert o["accuracy_label"] in ("ACCURATE", "PARTIAL", "INACCURATE", "PENDING")
    assert o["is_decision"] is False


# ── P148 Agent performance ──
def test_agent_performance_report_not_self_modifying():
    r = ap.report(objective="momentum research")
    assert set(r["agents"]) == {"ResearchDirector", "AnalystAgents", "ResearchReviewer", "ResearchWriter"}
    assert r["autonomous_self_modification"] is False
    assert 0.0 <= r["overall_effectiveness"] <= 1.0 and r["is_decision"] is False


# ── P150 v1.5 validation ──
def test_ops_validation_seven_checks():
    v = ov.validate_research_ops()
    names = {c["check"] for c in v["checks"]}
    assert names == {"scheduler_works", "agents_complete_research_tasks", "reports_generated",
                     "knowledge_updates_correctly", "human_review_required", "no_duplicate_systems",
                     "safety_rules_pass"}
    assert v["operational"] is True and v["safety"]["safe"] is True


def test_ops_safety_no_new_ledger():
    s = ov.ops_safety()
    assert s["safe"] is True and s["no_new_ledger"] is True and s["violations"] == []


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = rsch.plan_cycle("daily")
    b = rsch.plan_cycle("daily")
    assert a["tasks"] == b["tasks"] and a["assigned_agents"] == b["assigned_agents"]


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
