"""P121-130 연구 에이전트 OS 테스트 — Director·MarketAnalyst·CompanyAnalyst·StrategyResearcher·Reviewer·Writer·Workflow.

핵심: User Goal → Director → Specialists → Critic → Writer → Human Review. 모두 기존 엔진 재사용 ·
새 지능/DB/원장/메모리 없음 · 분석 전용 · 결정적 · 거래·집행·투자결정 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import agent_capability as ac
from jarvis.research_workflow import agent_validation as av
from jarvis.research_workflow import company_analyst as ca
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import market_analyst as ma
from jarvis.research_workflow import multi_agent_workflow as mw
from jarvis.research_workflow import research_director as rd
from jarvis.research_workflow import research_reviewer as rr
from jarvis.research_workflow import research_writer as rw
from jarvis.research_workflow import strategy_researcher as sr

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("agent_capability.py", "research_director.py", "market_analyst.py", "company_analyst.py",
            "strategy_researcher.py", "research_reviewer.py", "research_writer.py",
            "multi_agent_workflow.py", "agent_validation.py")
_SPEC = {"strategy_name": "tsmom", "feature_set": ["mom_12_1"], "universe": "US",
         "metrics": {"sharpe": 1.5, "out_of_sample": 0.5, "walk_forward": 0.6, "cost_impact": 0.02,
                     "parameter_stability": 0.7}}


# ── P121 Capability map ──
def test_capability_map_roles_and_analysis_only():
    c = ac.capability_map()
    assert c["count"] == 6 and c["role_hierarchy"] == ["director", "specialist", "critic", "report"]
    assert c["all_analysis_only"] is True and c["level"] == "RESEARCH_ONLY"
    for a in c["agents"]:
        assert a["used_engines"] and a["level"] == "RESEARCH_ONLY"
    assert c["is_decision"] is False


# ── P122 Director ──
def test_director_research_plan_fields():
    p = rd.plan("momentum in KR equities under high volatility")
    for f in ("objective", "hypothesis", "required_data", "assigned_agents", "validation_plan"):
        assert f in p, f
    agents = [a["agent"] for a in p["assigned_agents"]]
    assert "ResearchReviewer" in agents and "ResearchWriter" in agents
    assert p["is_decision"] is False


# ── P123 Market Analyst ──
def test_market_analyst_memo():
    m = ma.memo(topic="KR market", events=[{"kind": "macro", "text": "CPI surprise"}])
    assert m["memo_type"] == "Market Research Memo"
    assert "regime" in m["market_condition"] and m["is_trade_signal"] is False


# ── P124 Company Analyst ──
def test_company_analyst_memo():
    c = ca.memo("NVDA", financials=[{"company": "NVDA", "expected": {"eps": 0.5}, "actual": {"eps": 0.62}}],
                headlines=[{"text": "NVDA new AI chip", "entity": "NVDA"}])
    assert c["memo_type"] == "Company Research Memo"
    assert c["earnings"] and c["is_trade_signal"] is False


# ── P125 Strategy Researcher ──
def test_strategy_researcher_plan_no_auto_execution():
    s = sr.plan("momentum trend following")
    assert s["plan_type"] == "Strategy Research Plan" and s["experiment"]
    # 백테스트 잡은 사람 실행 대기(자동 실행 없음)
    assert s["backtest_job"].get("status") in ("CREATED", "WAITING_HUMAN")
    assert s["is_decision"] is False


# ── P126 Reviewer ──
def test_reviewer_evaluates_required_dimensions():
    v = rr.review(_SPEC, metrics=_SPEC["metrics"])
    for d in ("bias", "overfitting_risk", "missing_evidence", "weak_assumptions", "validation_quality"):
        assert d in v["dimensions"], d
    assert v["verdict"] in ("PASS", "WARN", "BLOCK") and v["is_decision"] is False


def test_reviewer_blocks_overfit():
    bad = {"strategy_name": "x", "metrics": {"sharpe": 2.0, "out_of_sample": 0.2}}
    v = rr.review(bad, metrics=bad["metrics"])
    assert v["verdict"] == "BLOCK" and v["blocks"] is True


# ── P127 Writer ──
def test_writer_seven_sections_confidence_limitations():
    v = rr.review(_SPEC, metrics=_SPEC["metrics"])
    w = rw.write("Does momentum work?", review=v, memos={"market": {"memo_type": "Market Research Memo"}})
    secs = list(w["report"])
    assert len(secs) == 7 and secs[0] == "1_research_question" and secs[-1] == "7_next_research_step"
    assert w["confidence"] in ("LOW", "MEDIUM", "HIGH") and w["limitations"]
    assert w["is_decision"] is False


# ── P128 Multi-agent workflow ──
def test_multi_agent_workflow_chain():
    wf = mw.run("momentum in KR equities", company="NVDA")
    assert wf["pipeline"] == ["Director", "Analyst", "StrategyResearcher", "Critic", "Writer"]
    assert len(wf["stages"]) >= 5 and wf["is_decision"] is False
    assert wf["requires_human_review"] is True and "report" in wf


def test_multi_agent_writes_existing_ledgers_only():
    wf = mw.run("test objective")
    assert "ledger_writes" in wf and wf["committed"] is False
    # 새 원장 없음
    assert len(wl.ALL_LEDGERS) == 3


# ── P130 Agent validation ──
def test_agent_system_validation():
    v = av.validate_agents()
    names = {c["check"] for c in v["checks"]}
    assert names == {"agents_use_existing_engines", "no_duplicated_intelligence",
                     "no_autonomous_decisions", "memory_updated_correctly",
                     "dashboard_displays_workflow"}
    assert v["validated"] is True and v["safety"]["safe"] is True


def test_agent_safety_no_new_ledger():
    s = av.agent_safety()
    assert s["safe"] is True and s["no_new_ledger"] is True and s["violations"] == []


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = rd.plan("momentum")
    b = rd.plan("momentum")
    assert a["assigned_agents"] == b["assigned_agents"] and a["hypothesis"] == b["hypothesis"]


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
