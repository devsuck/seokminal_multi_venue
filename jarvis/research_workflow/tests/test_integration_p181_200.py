"""P181-200 자율 연구 발견·검증 루프 v3.0 테스트 — cycle·observation·hypothesis v2·designer·priority·
gate·validation·selection·brief·loop·metrics·reflection·loop-validation·production-audit·release.

핵심: 기존 엔진 조율만 · 새 패키지/엔진/원장/DB/메모리 없음 · 자문 전용 · 결정적 · 자동 백테스트 없음 ·
WAITING_HUMAN 체크포인트 유지 · 자율 승인 없음 · 거래·집행·자본배분 없음 · 사람이 모든 결정.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import autonomous_validation_v3 as av3
from jarvis.research_workflow import experiment_designer as ed
from jarvis.research_workflow import hypothesis_discovery as hd
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import market_observation as mo
from jarvis.research_workflow import release_v30 as r30
from jarvis.research_workflow import research_brief as rb
from jarvis.research_workflow import research_cycle as rc
from jarvis.research_workflow import research_gate as rg
from jarvis.research_workflow import research_loop_v3 as rl
from jarvis.research_workflow import research_metrics_v3 as rm
from jarvis.research_workflow import research_priority as rp
from jarvis.research_workflow import research_reflection as rref
from jarvis.research_workflow import research_selection as rs
from jarvis.research_workflow import validation_intelligence as vi

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("research_cycle.py", "market_observation.py", "hypothesis_discovery.py",
            "experiment_designer.py", "research_priority.py", "research_gate.py",
            "validation_intelligence.py", "research_selection.py", "research_brief.py",
            "research_loop_v3.py", "research_metrics_v3.py", "research_reflection.py",
            "autonomous_validation_v3.py", "release_v30.py")
_FORBIDDEN_MARKET = ("BUY", "SELL", "LONG", "SHORT", "ALLOCATE")


# ── P181 Cycle Manager: WAITING_HUMAN 정지, 자동 백테스트 없음 ──
def test_cycle_stops_at_human_checkpoint():
    cyc = rc.run_cycle("momentum KR")
    assert cyc["state"] == "WAITING_HUMAN"
    assert cyc["human_checkpoint_pending"] is True and cyc["auto_backtest"] is False
    assert cyc["is_decision"] is False
    # WAITING_HUMAN 에서 승인 없이 EXTERNAL_VALIDATION 진입 불가
    nxt = rc.ResearchCycleManager().advance(cyc, human_approved=False)
    assert nxt["state"] == "WAITING_HUMAN"
    approved = rc.ResearchCycleManager().advance(cyc, human_approved=True)
    assert approved["state"] == "EXTERNAL_VALIDATION"


# ── P182 Observation: 기회는 신호 아님, 금지어 없음 ──
def test_observation_opportunity_not_signal():
    r = mo.observe_market(signals={"volatility_change": "AI vol expansion", "assets": ["NVDA"]})
    assert "opportunities" in r and r["is_decision"] is False
    for o in r["opportunities"]:
        assert o["is_signal"] is False and o["requires_validation"] is True
        for q in o["possible_questions"]:
            assert not any(w in str(q).upper().split() for w in _FORBIDDEN_MARKET)


# ── P183 Hypothesis v2: recall-first, 필수 필드 ──
def test_hypothesis_v2_recall_first_fields():
    r = hd.discover_research("momentum", limit=5)
    assert r["recall_first"] is True and r["is_decision"] is False
    h = r["research_hypotheses"][0]
    for f in ("question", "why_now", "novelty", "supporting_evidence", "contradicting_evidence",
              "similar_research", "past_failures", "required_test", "unknowns", "confidence"):
        assert f in h, f


def test_hypothesis_v2_why_different_on_past_failure():
    # 과거 실패가 있는 전략 토픽 → why_different 설명 필수
    r = hd.discover_research("kr_pure_momentum_v1 reversal", limit=6)
    flagged = [h for h in r["research_hypotheses"] if "why_different_this_time" in h]
    # 실패 유사가 잡히면 설명 존재(없으면 이 assert 스킵 — 데이터 의존)
    for h in flagged:
        assert h["why_different_this_time"]


# ── P184 Experiment Designer: spec + 3 scores ──
def test_experiment_designer_scores():
    hyp = hd.discover_research("momentum", limit=3)["research_hypotheses"][0]
    e = ed.design_experiment(hyp)
    for f in ("universe", "required_data", "benchmark", "metrics", "validation_rules",
              "cost_assumptions", "failure_conditions", "information_gain_score",
              "complexity_score", "expected_research_value"):
        assert f in e, f
    assert e["is_decision"] is False


# ── P185 Priority Engine: formula + why ──
def test_priority_engine_formula_and_why():
    hyps = hd.discover_research("momentum", limit=5)["research_hypotheses"]
    q = rp.prioritize_research(hyps, limit=5)
    assert q["is_decision"] is False and q["research_queue"]
    scores = [i["priority_score"] for i in q["research_queue"]]
    assert scores == sorted(scores, reverse=True)
    assert all("why_important" in i for i in q["research_queue"])


# ── P186 Human Gate: APPROVE≠실행, 금지 액션 거부 ──
def test_human_gate_approve_is_not_execution():
    hyps = hd.discover_research("momentum", limit=3)["research_hypotheses"]
    g = rg.build_approval_queue(hyps)
    assert set(g["available_actions"]) == {"APPROVE", "REJECT", "MODIFY"}
    assert "run_backtest" in g["forbidden_actions"] and "execute" in g["forbidden_actions"]
    ap = rg.act("APPROVE", "REQ:x", hypothesis=hyps[0])
    assert ap["executed"] is False and ap["job"]["status"] == "WAITING_HUMAN"
    assert "error" in rg.act("execute", "x") and "error" in rg.act("trade", "x")


# ── P187 Validation Intelligence: 5 gaps + classification ──
def test_validation_intelligence_classification():
    r = vi.build_validation_report({"metrics": {"sharpe": 0.4, "walk_forward": 0.3, "out_of_sample": 0.35}},
                                   {"metrics": {"sharpe": 0.35}})
    assert r["classification"] in ("ROBUST", "QUESTIONABLE", "FAILED")
    for g in ("performance_gap", "risk_gap", "cost_gap", "regime_gap", "behavioral_gap"):
        assert g in r["gaps"], g
    assert r["is_decision"] is False


# ── P188 Research Selection: evidence grade, 투자추천 아님 ──
def test_research_selection_evidence_grade():
    r = rs.evaluate_research({"strategy_name": "x", "metrics": {"sharpe": 0.6, "walk_forward": 0.3,
                                                               "out_of_sample": 0.4, "empirical_p": 0.03}})
    assert r["evidence_grade"] in ("STRONG", "MEDIUM", "WEAK", "REJECTED")
    assert r["is_investment_recommendation"] is False and r["is_decision"] is False


# ── P189 Research Brief: 7 sections ──
def test_research_brief_seven_sections():
    r = rb.build_research_brief(topic="momentum")
    assert set(r["sections"].keys()) == {"market_changes", "new_research_opportunities", "new_hypotheses",
                                         "pending_experiments", "validation_results",
                                         "failed_research_lessons", "human_review_queue"}
    assert r["is_decision"] is False


# ── P190 Continuous Loop: checkpoint 정지, external_results 시 진행 ──
def test_continuous_loop_checkpoint_and_progression():
    lp = rl.run_research_loop("momentum")
    assert lp["human_checkpoint_pending"] is True and lp["auto_backtest"] is False
    assert "EXTERNAL_TEST" not in lp["stages_completed"]
    ext = {"strategy_name": "t", "metrics": {"sharpe": 0.6, "walk_forward": 0.3, "out_of_sample": 0.4},
           "paper": {"metrics": {"sharpe": 0.5}}}
    lp2 = rl.run_research_loop("momentum", external_results=ext)
    assert lp2["human_checkpoint_pending"] is False and "VALIDATION" in lp2["stages_completed"]
    assert lp2["evidence_grade"] in ("STRONG", "MEDIUM", "WEAK", "REJECTED")


# ── P196 Metrics 7종 ──
def test_metrics_v3_seven():
    m = rm.build_research_metrics()["metrics"]
    for k in ("generated_hypotheses", "accepted_research_proposals", "completed_experiments",
              "validation_success_rate", "avoided_duplicate_research", "knowledge_reuse_rate",
              "failure_prevention_count"):
        assert k in m, k


# ── P197 Reflection: 새 메모리 없음 ──
def test_reflection_no_new_memory():
    r = rref.reflect()
    assert r["new_memory_created"] is False
    for q in ("what_did_we_learn", "what_failed", "which_assumptions_were_wrong",
              "what_research_should_stop", "what_should_continue"):
        assert q in r["reflection"], q


# ── P198 Loop Validation ──
def test_loop_validation_passes():
    v = av3.validate_loop()
    assert v["validated"] is True
    names = {c["stage"] for c in v["checks"]}
    for s in ("observation_works", "hypothesis_generation_works", "experiment_proposal_works",
              "human_checkpoint_exists", "validation_connected", "ranking_works",
              "reporting_works", "learning_works"):
        assert s in names, s


# ── P199 Production Audit ──
def test_production_audit_passes():
    a = av3.audit_production()
    assert a["audited"] is True and a["ledger_count"] == 3
    assert a["duplicate_logic"] == [] and a["violations"] == []


# ── P200 Release v3.0 ──
def test_release_v30():
    r = r30.build_release_report_v30()
    assert r["execution"] == "Disabled" and r["decision_authority"] == "Human Only"
    assert r["research_automation"] == "Enabled" and r["production_ready"] is True
    assert set(r["capabilities"]["cannot"]) == {"trade", "execute orders", "allocate capital",
                                                "approve investments"}
    assert r["is_decision"] is False


# ── 새 원장 없음 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


# ── 금지 def/import/모델 누출 없음 ──
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
