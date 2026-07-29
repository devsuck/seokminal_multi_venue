"""Agent Research Council(P59-60) 테스트 — 다관점 협의·합의/상충 탐지·균형 메모·신호 주입·안전.

핵심(문서 §Tests #6): 에이전트 관점이 상충을 식별한다 — Quant 지지 vs Critic 반대 → CONFLICT.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_assistant import ledger
from jarvis.research_assistant.council import (
    REC_CONFLICT,
    REC_INSUFFICIENT,
    ResearchCouncilEngine,
)
from jarvis.research_assistant.engine import ResearchAssistantEngine

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

# momentum: 실험 근거 있음(Quant SUPPORT) + 과거 실패 2건(Critic OPPOSE) → 상충
DATA = {
    "experiments": [{"name": "momentum study"}],
    "experiment_runs": [{"note": "momentum edge", "run_id": "r1"},
                        {"note": "momentum tuning", "run_id": "r2"}],
    "experiment_results": [{"metric": "sharpe", "value": 0.9, "note": "momentum"}],
    "failures": [{"reason": "momentum overfit in-sample"},
                 {"reason": "momentum regime change broke it"}],
    "incidents": [],
}


def _reader(name):
    return DATA.get(name, [])


@pytest.fixture()
def council(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    return ResearchCouncilEngine(ResearchAssistantEngine(reader=_reader))


def test_deliberate_returns_six_lenses(council):
    memo = council.deliberate("momentum")
    names = {ln["lens"] for ln in memo.lenses}
    assert {"Quant", "Risk", "Macro", "Supply", "News", "Critic"} <= names


def test_conflict_detected(council):
    memo = council.deliberate("momentum")
    assert memo.conflicts, "Quant 지지 vs Critic/Risk 경계 → 상충 감지"
    assert memo.recommendation == REC_CONFLICT
    assert memo.consensus is False


def test_memo_text_balanced(council):
    memo = council.deliberate("momentum")
    assert "Recommendation:" in memo.memo
    assert "Supportive:" in memo.memo and "Cautionary:" in memo.memo


def test_insufficient_basis_on_empty(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    c = ResearchCouncilEngine(ResearchAssistantEngine(reader=lambda n: []))
    memo = c.deliberate("some brand new idea")
    assert memo.recommendation == REC_INSUFFICIENT
    assert memo.conflicts == []


def test_signal_injection_overrides_lens(council):
    # event_intelligence 등 외부 결정적 신호 주입(Supply=공급망 리스크)
    memo = council.deliberate("momentum",
                              signals={"Supply": {"stance": "CAUTION",
                                                  "rationale": "TSMC dependency risk"}})
    supply = next(ln for ln in memo.lenses if ln["lens"] == "Supply")
    assert supply["stance"] == "CAUTION"
    assert "TSMC" in supply["rationale"]
    assert "Supply" in memo.cautionary


def test_signal_injection_adds_new_lens(council):
    memo = council.deliberate("momentum",
                              signals={"Valuation": {"stance": "OPPOSE",
                                                     "rationale": "rich multiple"}})
    assert any(ln["lens"] == "Valuation" for ln in memo.lenses)


def test_advisory(council):
    memo = council.deliberate("momentum")
    d = memo.to_dict()
    assert d["is_advisory"] is True and d["is_decision"] is False
    assert d["requires_human_judgment"] is True


def test_record_memo_writes_note(council):
    memo = council.deliberate("momentum")
    rec = council.record_memo(memo, now="2026-01-01T00:00:00Z", commit=True)
    from jarvis.research_assistant import ledger as al
    assert len(al.read_notes()) == 1
    assert rec.is_binding is False


def test_deterministic(council):
    a = council.deliberate("momentum").to_dict()
    b = council.deliberate("momentum").to_dict()
    assert a["recommendation"] == b["recommendation"]
    assert a["conflicts"] == b["conflicts"]


# ── 안전 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "council.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "council.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_engine_no_execution_methods(council):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(council, m)


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "council.py").read().lower()
