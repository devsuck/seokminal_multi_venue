"""Workflow Orchestrator(P64) 테스트 — 조율·부분완료·resume·cancel·retry·사람결정·해시체인·안전.

핵심(문서 §Tests #1,#2,#5,#6): 워크플로 조율·resume·중복원장 없음·사람 승인 필수.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_workflow import ledger
from jarvis.research_workflow import models as M
from jarvis.research_workflow.orchestrator import WorkflowCancelledError, WorkflowOrchestrator
from jarvis.research_workflow.verify import verify_chain

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

DATA = {"experiments": [{"name": "momentum study"}],
        "experiment_runs": [{"note": "momentum edge"}],
        "failures": [{"reason": "momentum overfit"}, {"reason": "momentum regime"}]}
_FULL = {"sharpe": 0.9, "return": 0.1, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}
_BT = {"strategy_name": "momentum", "metrics": dict(_FULL)}


@pytest.fixture()
def orch(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda n: str(state / n))
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    return WorkflowOrchestrator(assistant=ResearchAssistantEngine(reader=lambda n: DATA.get(n, [])))


def _full_ctx():
    return {"topic": "momentum", "design": True, "backtest": _BT, "metrics": dict(_FULL),
            "paper": {"return": 0.04, "cost_impact": 0.4}, "strategies": [],
            "new_strategy": {"name": "m", "exposures": {"sector": {"semi": 0.8}}},
            "portfolio": {"exposures": {"sector": {"semi": 0.35}}, "weight_new": 0.2}}


# ── 1. 조율 ──
def test_full_orchestration(orch):
    st = orch.run("research momentum", _full_ctx(), now=NOW, commit=True)
    assert st.completed_stages[:4] == [M.S_REQUEST, M.S_QUEUE, M.S_RECALL, M.S_COUNCIL]
    assert M.S_DECISION in st.completed_stages
    assert st.requires_human_decision is True
    assert st.current_stage == M.S_HUMAN


def test_deterministic_execution_log(orch):
    st = orch.run("research momentum", _full_ctx(), now=NOW, commit=True)
    stages = [e["stage"] for e in st.execution_log]
    assert stages[0] == M.S_REQUEST
    assert all("output_digest" in e for e in st.execution_log)


# ── 부분 완료(외부 입력 없음 → BLOCKED) ──
def test_partial_completion_blocks_on_design(orch):
    st = orch.run("research momentum", {"topic": "momentum"}, now=NOW, commit=True)
    assert st.blocked_stage == M.S_DESIGN
    assert M.S_COUNCIL in st.completed_stages
    assert M.S_DECISION not in st.completed_stages


# ── 2. resume ──
def test_resume_after_input_provided(orch):
    st = orch.run("research momentum", {"topic": "momentum"}, now=NOW, commit=True)
    run_id = st.run_id
    assert st.blocked_stage == M.S_DESIGN
    # 입력이 생긴 뒤 재개 → 끝까지 진행
    st2 = orch.resume(run_id, "research momentum", _full_ctx(), now=NOW, commit=True)
    assert M.S_DESIGN in st2.completed_stages
    assert M.S_DECISION in st2.completed_stages
    assert st2.requires_human_decision is True


def test_resume_does_not_rerun_completed(orch):
    orch.run("r", {"topic": "momentum"}, now=NOW, commit=True)
    run_id = orch.run("r", {"topic": "momentum"}, now=NOW, commit=True).run_id
    before = len([e for e in ledger.run_events(run_id) if e["stage"] == M.S_COUNCIL])
    orch.resume(run_id, "r", _full_ctx(), now=NOW, commit=True)
    after = len([e for e in ledger.run_events(run_id) if e["stage"] == M.S_COUNCIL])
    assert after == before   # 완료 단계는 재실행/재기록 안 함


# ── retry ──
def test_retry_stage(orch):
    st = orch.run("r", {"topic": "momentum"}, now=NOW, commit=True)
    st2 = orch.retry(st.run_id, "r", M.S_DESIGN, _full_ctx(), now=NOW, commit=True)
    assert M.S_DECISION in st2.completed_stages


# ── cancel ──
def test_cancel_blocks_further(orch):
    st = orch.run("r", {"topic": "momentum"}, now=NOW, commit=True)
    c = orch.cancel(st.run_id, "not needed", now=NOW, commit=True)
    assert c.cancelled is True
    with pytest.raises(WorkflowCancelledError):
        orch.resume(st.run_id, "r", _full_ctx(), now=NOW, commit=True)


# ── 6. 사람 결정 필수(엔진은 승인 안 함) ──
def test_human_decision_required_reviewer(orch):
    st = orch.run("research momentum", _full_ctx(), now=NOW, commit=True)
    with pytest.raises(ValueError):
        orch.record_human_decision(st.run_id, "APPROVED", "", now=NOW, commit=True)


def test_human_decision_records(orch):
    st = orch.run("research momentum", _full_ctx(), now=NOW, commit=True)
    rec = orch.record_human_decision(st.run_id, "approved", "researcher_kim", now=NOW, commit=True)
    assert rec["is_human"] is True and rec["decision"] == "APPROVED"
    assert orch.state(st.run_id).requires_human_decision is False


# ── 해시체인·원장 ──
def test_hash_chain_valid(orch):
    orch.run("research momentum", _full_ctx(), now=NOW, commit=True)
    res = verify_chain()
    assert res["ok"]


# ── 5. 중복 원장 없음 ──
def test_no_duplicate_ledgers(orch, tmp_path):
    orch.run("research momentum", _full_ctx(), now=NOW, commit=True)
    assert ledger.ALL_LEDGERS == (("rwf_runs.jsonl", "event_id"),
                                  ("rwf_sessions.jsonl", "event_id"))
    # 조율은 기존 실험/메모리 원장에 쓰지 않는다(rwf_ 만)
    written = {p.name for p in (tmp_path / "_state").iterdir()}
    assert written <= {"rwf_runs.jsonl", "rwf_sessions.jsonl"}


def test_dry_run_no_writes(orch, tmp_path):
    orch.run("research momentum", _full_ctx(), now=NOW, commit=False)
    assert not (tmp_path / "_state").exists() or list((tmp_path / "_state").iterdir()) == []


def test_advisory(orch):
    st = orch.run("r", _full_ctx(), now=NOW, commit=True)
    assert st.is_advisory is True and st.is_decision is False


# ── 안전 ──
def test_no_forbidden_imports():
    for f in ("orchestrator.py", "decision_support.py", "session_manager.py",
              "explainability.py", "_evidence.py"):
        tree = ast.parse(open(SRC / f).read())
        bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
               "jarvis.live_trading", "jarvis.portfolio_execution")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in bad), (f, node.module)


def test_no_dangerous_defs():
    for f in ("orchestrator.py", "decision_support.py", "session_manager.py",
              "explainability.py", "_evidence.py"):
        tree = ast.parse(open(SRC / f).read())
        bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in bad, (f, node.name)


def test_no_model_id_leak():
    for f in ("orchestrator.py", "decision_support.py", "session_manager.py",
              "explainability.py", "_evidence.py", "models.py"):
        assert MODEL_LEAK_TOKEN not in open(SRC / f).read().lower()
