"""P201 Forward Prediction Registry + Writer Authority Protocol 테스트.

핵심 계약: framework 는 strategy_family 에서 결정적 유도(선택 불가) · 4결과(RIGHT/WRONG/INVALIDATED/
INCONCLUSIVE, INVALIDATED≠실패) · 모든 confidence 기록(생존편향 차단) · success_rule 사전등록 불변 ·
기존 rmi_ 원장만(새 원장 없음) · 자문 전용 · 결정적.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import ledger_writer as lw
from jarvis.research_workflow import prediction_registry as pr

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("prediction_registry.py", "ledger_writer.py")
_N = "2026-07-26T00:00:00Z"


class _MemDriver:
    def __init__(self):
        self.d = {}

    def read(self):
        return dict(self.d)

    def write(self, l):
        self.d = dict(l)

    def clear(self):
        self.d = {}


# ── framework 는 strategy_family 에서 결정적 유도(capturer 선택 불가) ──
def test_framework_derived_from_family_not_chosen():
    assert pr.derive_framework("event")["framework"] == "abnormal_return"
    assert pr.derive_framework("factor")["primary_metric"] == "IC"
    assert pr.derive_framework("momentum")["framework"] == "risk_adjusted_vs_baseline"
    # 미지 family → baseline_relative(절대수익 아님)
    assert pr.derive_framework("nonsense")["framework"] == "baseline_relative"
    # capture 도 family 로만 결정 — 같은 family면 항상 같은 framework
    a = pr.capture_prediction(thesis="x", strategy_family="event", now=_N)
    b = pr.capture_prediction(thesis="y", strategy_family="event", now=_N)
    assert a["evaluation_framework"] == b["evaluation_framework"]


# ── 사전등록 불변: success_rule/framework/thresholds 동결 + 해시 ──
def test_capture_freezes_success_rule_and_all_confidence():
    s = pr.capture_prediction(thesis="buyback drift", strategy_id="kr_x", strategy_family="event",
                              confidence="LOW", source="automatic_discovery",
                              invalidation_condition="random 못 넘으면 폐기", now=_N)
    assert s["state"] == "PENDING" and s["outcome"] is None
    assert s["success_rule"]["fail_if_invalidation_triggered"] is True
    assert s["success_rule"]["inconclusive_if_insufficient_data"] is True
    assert "evaluation_framework" in s["immutable_fields"] and "success_rule" in s["immutable_fields"]
    assert s["snapshot_hash"].startswith("sha256:")
    # LOW confidence 도 기록됨(STRONG만 아님 — 생존편향 차단)
    assert s["confidence"] == "LOW" and s["is_decision"] is False


def test_capture_deterministic():
    a = pr.capture_prediction(thesis="t", strategy_id="s", strategy_family="momentum", now=_N)
    b = pr.capture_prediction(thesis="t", strategy_id="s", strategy_family="momentum", now=_N)
    assert a["prediction_id"] == b["prediction_id"] and a["snapshot_hash"] == b["snapshot_hash"]


# ── 4결과: RIGHT/WRONG/INVALIDATED/INCONCLUSIVE, INVALIDATED≠실패 ──
def test_evaluate_four_outcomes_via_frozen_rule(monkeypatch):
    snap = pr.capture_prediction(thesis="t", strategy_id="s", strategy_family="event", now=_N)
    monkeypatch.setattr(pr, "get_prediction", lambda pid: snap)
    pid = snap["prediction_id"]
    assert pr.evaluate(pid, {"baseline_outperformance": True, "thesis_held": True}, now=_N)["outcome"] == "RIGHT"
    assert pr.evaluate(pid, {"baseline_outperformance": False, "thesis_held": True}, now=_N)["outcome"] == "WRONG"
    inval = pr.evaluate(pid, {"invalidation_triggered": True}, now=_N)
    assert inval["outcome"] == "INVALIDATED" and inval["invalidated_is_not_failure"] is True
    incon = pr.evaluate(pid, {"insufficient_data": True}, now=_N)
    assert incon["outcome"] == "INCONCLUSIVE"


def test_evaluate_uses_frozen_rule_only(monkeypatch):
    # capture 시점 규칙만 사용 — 평가 시 새 규칙 주입 불가(사후 편향 차단)
    snap = pr.capture_prediction(thesis="t", strategy_family="macro", now=_N)
    monkeypatch.setattr(pr, "get_prediction", lambda pid: snap)
    r = pr.evaluate(snap["prediction_id"], {"baseline_outperformance": True, "thesis_held": True}, now=_N)
    assert r["used_frozen_rule"] is True and r["is_decision"] is False


# ── 생명주기 전이 ──
def test_transition_states_and_outcomes():
    r = pr.transition("PRED:abc", "EVALUATED", outcome="RIGHT", now=_N)
    assert r["to_state"] == "EVALUATED" and r["outcome"] == "RIGHT"
    assert "error" in pr.transition("PRED:abc", "BOGUS", now=_N)
    assert "error" in pr.transition("PRED:abc", "EVALUATED", outcome="BOGUS", now=_N)


# ── Writer Authority Protocol: 단일 활성 writer, 충돌 거부, 만료 핸드오프 ──
def test_writer_authority_single_writer_and_conflict():
    wa = lw.WriterAuthority(driver=_MemDriver())
    assert wa.acquire("macbook", "s1", now=_N)["acquired"] is True
    rej = wa.acquire("server2", "s2", now=_N)
    assert rej["rejected"] is True and rej["acquired"] is False
    assert wa.has_authority("macbook", now=_N) and not wa.has_authority("server2", now=_N)
    # 만료 후 재획득 가능
    assert wa.acquire("server2", "s3", now="2026-07-26T02:00:00Z")["acquired"] is True


def test_writer_guarded_append_requires_authority():
    wa = lw.WriterAuthority(driver=_MemDriver())
    wa.acquire("macbook", now=_N)
    ok = wa.guarded_append("macbook", lambda: "wrote", now=_N)
    assert ok["rejected"] is False and ok["result"] == "wrote"
    bad = wa.guarded_append("intruder", lambda: "wrote", now=_N)
    assert bad["rejected"] is True


# ── registry_status: 생존편향 방지(graded vs pending, 표본 게이트) ──
def test_registry_status_shape():
    st = pr.registry_status()
    for k in ("total_predictions", "by_confidence", "by_source", "by_state", "by_outcome",
              "graded", "scorable_right_wrong", "pending", "sufficient_sample_for_score",
              "captures_all_confidence"):
        assert k in st, k
    assert st["captures_all_confidence"] is True and st["min_graded_sample"] == 20
    assert st["is_decision"] is False


# ── 새 원장 없음(예측은 기존 rmi_ 재사용) ──
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
