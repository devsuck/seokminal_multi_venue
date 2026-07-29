"""P161-170 기관 투자위원회 & 생산 준비 테스트 — committee·debate·conviction·portfolio·decision center·production·metrics·governance·system·release.

핵심: Research Report → Committee → Human Decision. 모두 기존 엔진 재사용 · 새 DB/원장/메모리/엔진 없음 ·
자문 전용 · 결정적 · 거래·집행·배분·승인 없음. **아키텍처 동결.**
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import conviction_framework as cf
from jarvis.research_workflow import debate_engine as de
from jarvis.research_workflow import governance as gv
from jarvis.research_workflow import human_decision_center as dc
from jarvis.research_workflow import investment_committee as ic
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import operational_metrics as om
from jarvis.research_workflow import portfolio_research_view as pr
from jarvis.research_workflow import production_monitor as pm
from jarvis.research_workflow import release_v20 as rv
from jarvis.research_workflow import system_validation as sv

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("investment_committee.py", "debate_engine.py", "conviction_framework.py",
            "portfolio_research_view.py", "human_decision_center.py", "production_monitor.py",
            "operational_metrics.py", "governance.py", "system_validation.py", "release_v20.py")
# 위원회는 절대 BUY/SELL/EXECUTE/ALLOCATE 를 출력하지 않는다
_FORBIDDEN_OUTPUT = ("BUY", "SELL", "EXECUTE", "ALLOCATE")


# ── P161 Committee ──
def test_committee_packet_fields_no_buy_sell():
    c = ic.build_committee_packet("Does momentum work in KR equities?")
    for f in ("research_summary", "supporting_evidence", "risk_summary", "alternative_views",
              "confidence", "limitations", "questions_for_human"):
        assert f in c, f
    assert c["requires_human_review"] is True and c["is_decision"] is False
    # 최상위 값에 BUY/SELL/EXECUTE/ALLOCATE 같은 지시가 없어야 함
    assert str(c.get("research_summary", "")).upper() not in _FORBIDDEN_OUTPUT


# ── P162 Debate ──
def test_debate_report_six_cases():
    d = de.build_debate("momentum trend following")
    for f in ("bull_case", "bear_case", "risk_case", "alternative_explanation", "missing_evidence",
              "historical_counterexamples"):
        assert f in d, f
    assert d["is_decision"] is False


# ── P163 Conviction ──
def test_conviction_levels_not_investment_rating():
    c = cf.build_conviction("momentum")
    assert set(c["factors"]) == {"evidence_quality", "historical_similarity", "knowledge_consistency",
                                 "risk_level", "uncertainty", "validation_quality"}
    assert c["conviction_level"] in ("LOW", "MEDIUM", "HIGH")
    assert c["is_investment_rating"] is False and c["is_decision"] is False


# ── P164 Portfolio research ──
def test_portfolio_research_no_allocation():
    p = pr.build_portfolio_research(strategies=["tsmom", "vwap_reversion"], correlations={"A~B": 0.7})
    for f in ("sector_exposure", "factor_exposure", "strategy_overlap", "correlation", "concentration",
              "scenario_comparison"):
        assert f in p, f
    assert "allocation" not in p and p["is_decision"] is False


# ── P165 Decision center ──
def test_decision_center_forbidden_actions():
    d = dc.build_decision_center("Does momentum work?")
    assert set(d["available_actions"]) == {"review", "comment", "request_followup", "archive"}
    assert "approve_trade" in d["forbidden_actions"] and "execute" in d["forbidden_actions"]
    # 금지 액션은 거부
    assert "error" in dc.act("approve_trade", "x")
    assert "error" in dc.act("allocate", "x")
    # 허용 액션은 비구속
    assert dc.act("comment", "x", comment="ok")["is_binding"] is False


# ── P166 Production monitor ──
def test_production_status_severity():
    p = pm.build_production_status()
    assert p["overall_severity"] in ("OK", "WARNING", "CRITICAL")
    assert len(p["components"]) == 7
    for c in p["components"]:
        assert c["severity"] in ("OK", "WARNING", "CRITICAL")


# ── P167 Operational metrics ──
def test_operational_metrics_seven():
    m = om.build_operational_metrics()["metrics"]
    for k in ("research_throughput", "research_latency", "agent_utilization", "api_availability",
              "data_freshness", "research_completion", "review_backlog"):
        assert k in m, k


# ── P168 Governance ──
def test_governance_compliant():
    g = gv.build_governance()
    names = {c["check"] for c in g["checks"]}
    assert names == {"permissions", "audit_trail", "append_only_integrity", "human_checkpoints",
                     "architecture_compliance", "safety_rules"}
    assert g["passed"] is True and g["governance"] == "COMPLIANT"


# ── P169 System validation ──
def test_system_validation_seven_checks():
    v = sv.validate_system()
    names = {c["check"] for c in v["checks"]}
    assert names == {"workflow_complete", "committee_works", "governance_passes", "monitoring_healthy",
                     "metrics_generated", "dashboard_integrated", "no_duplicated_architecture"}
    assert v["validated"] is True


# ── P170 Release ──
def test_release_v20_frozen_ready():
    r = rv.build_release_report()
    assert r["architecture_frozen"] is True and r["release_ready"] is True
    for k in ("architecture_summary", "capability_matrix", "production_checklist", "safety_checklist",
              "known_limitations", "deployment_notes", "future_operating_guidance"):
        assert k in r, k
    assert r["is_decision"] is False


# ── 결정적 + 중복원장 없음 + 안전 스캔 ──
def test_deterministic():
    a = cf.build_conviction("momentum")
    b = cf.build_conviction("momentum")
    assert a["conviction_level"] == b["conviction_level"] and a["factors"] == b["factors"]


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
                                         "place_order", "deploy_strategy"), (f, node.name)
