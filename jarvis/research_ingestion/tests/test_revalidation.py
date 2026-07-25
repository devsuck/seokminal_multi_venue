"""Research Re-validation(P57) 테스트 — 진단·승격·조작금지·하네스부재·backlog·안전.

핵심: 누락 검증은 하네스가 실제 산출한 값으로만 채워지고, 하네스가 없으면 INCOMPLETE 로 남는다(조작 금지).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.engine import ResearchIngestionEngine
from jarvis.research_ingestion.revalidation import ResearchRevalidationEngine

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

_MISSING_5 = {"walk_forward", "out_of_sample", "cost_impact", "parameter_stability",
              "random_baseline"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return ResearchRevalidationEngine(ResearchIngestionEngine())


def _incomplete_rec():
    return {"strategy_name": "Momentum_v1", "strategy_version": "v1",
            "universe": "KR", "metrics": {"return": 0.1, "sharpe": 0.6,
                                          "max_drawdown": -0.15, "volatility": 0.14}}


def _full_harness(rec):
    # 실제 검증 하네스가 산출했다고 가정하는 누락 5종(성공 케이스)
    return {"walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
            "parameter_stability": 0.8, "random_baseline": 0.2}


# ── 진단(plan) ──
def test_plan_identifies_missing(env):
    plan = env.plan(_incomplete_rec())
    assert set(plan.missing) == _MISSING_5
    assert plan.revalidatable is True
    assert plan.validation_complete is False


def test_plan_complete_record(env):
    rec = _incomplete_rec()
    rec["metrics"].update(_full_harness(rec))
    plan = env.plan(rec)
    assert plan.missing == []
    assert plan.validation_complete is True


# ── 하네스 없음 → INCOMPLETE 유지(조작 금지) ──
def test_no_harness_stays_incomplete(env):
    res = env.revalidate(_incomplete_rec(), harness=None, now=NOW, commit=True)
    assert res.status == "UNAVAILABLE"
    assert res.upgraded is False
    assert res.filled == []
    assert ledger.read_ingestions() == []       # 아무것도 쓰지 않음


# ── 하네스로 전부 채움 → COMPLETE 승격 ──
def test_full_harness_upgrades(env):
    res = env.revalidate(_incomplete_rec(), harness=_full_harness, now=NOW, commit=True)
    assert res.status == "COMPLETE"
    assert set(res.filled) == _MISSING_5
    assert res.missing_after == []
    assert res.upgraded is True
    assert res.new_outcome in M.OUTCOMES
    assert len(ledger.read_ingestions()) == 1   # 승격본이 새 판정 실험으로 기록
    from jarvis.experiment_tracking import ledger as el
    runs = el.read_runs()
    assert any("reval" in str(r.get("code_version", "")) for r in runs)


# ── 부분만 채움 → 여전히 INCOMPLETE ──
def test_partial_harness_stays_incomplete(env):
    res = env.revalidate(_incomplete_rec(),
                         harness=lambda r: {"walk_forward": 0.8}, now=NOW, commit=True)
    assert res.filled == ["walk_forward"]
    assert res.status == "INCOMPLETE"
    assert "out_of_sample" in res.missing_after


# ── 하네스가 조작/무관 값 반환 → 무시(조작 방지) ──
def test_harness_fabrication_ignored(env):
    # 누락 집합에 없는 키(sharpe 는 이미 있음) + 비수치는 병합하지 않음
    res = env.revalidate(_incomplete_rec(),
                         harness=lambda r: {"sharpe": 9.9, "walk_forward": "N/A",
                                            "random_baseline": None}, now=NOW, commit=True)
    assert res.filled == []                      # 유효한 누락 수치 없음
    assert res.status == "INCOMPLETE"
    assert ledger.read_ingestions() == []


# ── 이미 완전 → ALREADY_COMPLETE ──
def test_already_complete(env):
    rec = _incomplete_rec()
    rec["metrics"].update(_full_harness(rec))
    res = env.revalidate(rec, harness=_full_harness, now=NOW, commit=True)
    assert res.status == "ALREADY_COMPLETE"
    assert res.upgraded is False


# ── backlog: 원장의 INCOMPLETE 목록 ──
def test_incomplete_backlog(env):
    ing = ResearchIngestionEngine()
    ing.ingest({"strategy_name": "IncA", "metrics": {"sharpe": 0.5}}, NOW, commit=True)
    ing.ingest({"strategy_name": "CompB", "metrics": {**_incomplete_rec()["metrics"],
                **_full_harness(None)}}, NOW, commit=True)
    bl = env.incomplete_backlog()
    names = {i["strategy_name"] for i in bl.items}
    assert "IncA" in names
    assert "CompB" not in names


def test_result_advisory(env):
    res = env.revalidate(_incomplete_rec(), harness=_full_harness, now=NOW, commit=True)
    assert res.is_advisory is True
    assert res.is_decision is False


# ── 안전 스캔 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "revalidation.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "revalidation.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "revalidation.py").read().lower()
