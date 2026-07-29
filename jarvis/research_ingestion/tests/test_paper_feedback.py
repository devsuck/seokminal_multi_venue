"""Paper Trading Feedback(P63) 테스트 — 차이 분석·원인 추론·메모리 연결·recall 회수·자문·안전.

핵심(문서 §Tests #5,#6): 페이퍼 결과가 메모리에 저장되고, assistant 가 '백테스트 밖에서도 됐어?'에 답한다.
페이퍼만 — 라이브 브로커·집행·자본배분 없음(이 모듈은 페이퍼를 실행하지 않고 결과만 소비).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_ingestion.paper_feedback import PAPER_MARKER, PaperTradingFeedback

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """rmi_·research_assistant 원장을 같은 tmp _state 로 격리."""
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
    return PaperTradingFeedback(ResearchMemoryIntelligenceEngine())


# ── 차이 분석 ──
def test_compare_transaction_cost_cause(env):
    diff = env.compare({"return": 0.15},
                       {"return": 0.04, "cost_impact": 0.4, "turnover": 0.6})
    assert diff.return_gap == round(0.04 - 0.15, 4)
    assert "transaction" in diff.cause.lower() or "liquidity" in diff.cause.lower()
    assert diff.severity == "HIGH"


def test_compare_gap_ratio(env):
    diff = env.compare({"return": 0.10}, {"return": 0.05})
    assert diff.gap_ratio == round(-0.05 / 0.10, 4)


def test_compare_outperformance(env):
    diff = env.compare({"return": 0.05}, {"return": 0.08})
    assert diff.return_gap > 0
    assert diff.severity == "LOW"


# ── 피드백 저장(Experiment·Strategy·Risk·Lesson) ──
def test_record_feedback_writes_lesson_and_failure(env):
    res = env.record_feedback("TSMOM", {"return": 0.15},
                              {"return": 0.04, "cost_impact": 0.4, "turnover": 0.6},
                              experiment_id="XT:exp1", risk_ref="rr:1", now=NOW, commit=True)
    assert res.memory_written == "lesson+failure"    # 심각 하회 → 실패 메모리도
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_lessons()) == 1
    assert len(ml.read_failures()) == 1


def test_small_gap_lesson_only(env):
    res = env.record_feedback("EMA", {"return": 0.10}, {"return": 0.09}, now=NOW, commit=True)
    assert res.memory_written == "lesson"
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_failures()) == 0


# ── recall: "이 전략, 백테스트 밖에서도 됐어?" (Test req #6) ──
def test_did_it_work_outside_backtest(env):
    env.record_feedback("TSMOM", {"return": 0.15},
                        {"return": 0.04, "cost_impact": 0.4, "turnover": 0.6}, now=NOW, commit=True)
    ans = env.did_it_work_outside_backtest("TSMOM")
    assert ans["has_paper_evidence"] is True
    assert ans["paper_observations"]
    assert PAPER_MARKER.lower() in ans["paper_observations"][0]["text"].lower()


def test_no_paper_evidence(env):
    ans = env.did_it_work_outside_backtest("NeverPapered")
    assert ans["has_paper_evidence"] is False


def test_failure_intelligence_sees_paper_shortfall(env):
    env.record_feedback("TSMOM", {"return": 0.15},
                        {"return": 0.04, "cost_impact": 0.4, "turnover": 0.6}, now=NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    fi = ResearchAssistantEngine().failure_intelligence()
    assert fi.total_failures >= 1


def test_feedback_advisory(env):
    res = env.record_feedback("X", {"return": 0.1}, {"return": 0.1}, now=NOW, commit=True)
    assert res.is_advisory is True and res.is_decision is False


def test_dry_run_no_write(env):
    env.record_feedback("X", {"return": 0.15}, {"return": 0.04}, now=NOW, commit=False)
    from jarvis.research_memory_intelligence import ledger as ml
    assert ml.read_lessons() == []


# ── 안전 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "paper_feedback.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "paper_feedback.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "paper_feedback.py").read().lower()
