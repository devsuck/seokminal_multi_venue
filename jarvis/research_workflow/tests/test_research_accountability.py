"""Research Accountability Loop 테스트 — forward eval(frozen rule만)·decay·batting·edge·lifecycle.

핵심: 평가는 항상 박제된 frozen success_rule 로만(사후·골대이동 없음) · Pending/Evaluated/Invalidated/
Inconclusive 항상 분리(pending 숨김 없음) · confidence decay · edge score PROVISIONAL<20 · 새 원장 없음 · 실행 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import prediction_registry as pr
from jarvis.research_workflow import research_accountability as ra

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_N = "2026-08-01T00:00:00Z"


# ── Forward evaluation: frozen rule 만, 4 outcomes ──
def test_forward_eval_four_outcomes(monkeypatch):
    snap = pr.capture_prediction(thesis="t", strategy_family="momentum", now="2026-07-01T00:00:00Z")
    monkeypatch.setattr(pr, "get_prediction", lambda pid: snap)
    pid = snap["prediction_id"]
    assert ra.evaluate_forward(pid, {"baseline_outperformance": True, "thesis_held": True}, now=_N)["outcome"] == "RIGHT"
    assert ra.evaluate_forward(pid, {"baseline_outperformance": False, "thesis_held": True}, now=_N)["outcome"] == "WRONG"
    assert ra.evaluate_forward(pid, {"invalidation_triggered": True}, now=_N)["outcome"] == "INVALIDATED"
    assert ra.evaluate_forward(pid, {"insufficient_data": True}, now=_N)["outcome"] == "INCONCLUSIVE"


def test_forward_eval_no_goalpost_movement(monkeypatch):
    # forward_result 에 새 규칙을 주입해도 무시 — frozen rule 만 사용
    snap = pr.capture_prediction(thesis="t", strategy_family="momentum", now="2026-07-01T00:00:00Z")
    monkeypatch.setattr(pr, "get_prediction", lambda pid: snap)
    r = ra.evaluate_forward(snap["prediction_id"],
                            {"baseline_outperformance": False, "thesis_held": True,
                             "success_rule": {"require_baseline_outperformance": False}}, now=_N)
    assert r["outcome"] == "WRONG" and r["used_frozen_rule"] is True   # 주입 규칙 무시


def test_forward_batch(monkeypatch):
    snap = pr.capture_prediction(thesis="t", strategy_family="event", now="2026-07-01T00:00:00Z")
    monkeypatch.setattr(pr, "get_prediction", lambda pid: snap)
    b = ra.evaluate_forward_batch({snap["prediction_id"]: {"baseline_outperformance": True, "thesis_held": True}}, now=_N)
    assert b["evaluated"] == 1 and b["no_posthoc"] is True and b["used_frozen_rule"] is True


# ── Confidence decay ──
def test_confidence_decay_within_and_expired():
    fresh = ra.confidence_decay({"captured_at": "2026-07-29T00:00:00Z", "expected_horizon": "3M",
                                 "confidence": "HIGH"}, now=_N)
    assert fresh["status"] == "WITHIN_HORIZON" and fresh["factor"] == 1.0
    expired = ra.confidence_decay({"captured_at": "2026-01-01T00:00:00Z", "expected_horizon": "3M",
                                   "confidence": "HIGH"}, now=_N)
    assert expired["status"] == "EXPIRED" and expired["factor"] == 0.0


def test_horizon_parsing():
    assert ra._horizon_days("3M") == 90 and ra._horizon_days("1Y") == 365
    assert ra._horizon_days("") == 90   # 기본


# ── Accountability report: pending 항상 분리, 절대 숨김 없음 ──
def test_report_never_hides_pending():
    r = ra.accountability_report(now=_N)
    for bucket in ("pending", "evaluated", "invalidated", "inconclusive"):
        assert bucket in r["lifecycle"], bucket
    assert r["hides_pending"] is False
    assert r["evaluation_rule"] == "frozen_success_rule_only"
    assert r["no_posthoc_evaluation"] is True and r["no_goalpost_movement"] is True
    assert r["is_decision"] is False


def test_report_batting_average_honest_when_unevaluated():
    r = ra.accountability_report(now=_N)
    # 미평가면 batting average 는 None(정직 — 억지 숫자 없음)
    if r["lifecycle"]["evaluated"] == 0:
        assert r["batting_average"]["value"] is None


def test_edge_score_provisional_gate():
    r = ra.accountability_report(now=_N)
    # graded<20 이면 PROVISIONAL, 숫자 없음
    if (r["edge_score"]["graded_scorable"] or 0) < 20:
        assert r["edge_score"]["status"] == "PROVISIONAL" and r["edge_score"]["score"] is None


# ── 새 원장 없음 + 금지 스캔 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


def test_no_forbidden_defs_imports_leak():
    src = open(SRC / "research_accountability.py").read()
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
