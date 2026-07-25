"""Research Queue Engine(P58) 테스트 — 후보 생성·미탐색 조합·실패 강건화·이벤트·레짐·자문·안전.

핵심: Jarvis 가 다음 연구 후보를 결정적으로 제안하되 **사람 승인 없이 실행하지 않는다**.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.research_assistant import ledger
from jarvis.research_assistant.engine import ResearchAssistantEngine
from jarvis.research_assistant.research_queue import (
    HIGH,
    K_COMBINATION,
    K_EVENT,
    K_FAILURE_FIX,
    ResearchQueueEngine,
)

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

# 개별 신호는 시도됨(insider, supply, momentum, liquidity), 일부 조합은 미탐색
DATA = {
    "experiments": [
        {"name": "insider signal study"},
        {"name": "supply chain momentum"},
        {"name": "liquidity factor test"},
    ],
    "experiment_runs": [
        {"code_version": "insider", "note": "insider edge"},
        {"code_version": "liquidity", "note": "liquidity screen"},
    ],
    "failures": [{"reason": "cost sensitivity too high"},
                 {"reason": "cost sensitivity turnover"},
                 {"reason": "cost sensitivity fees"}],
    "incidents": [],
    "experiment_results": [],
}


def _reader(name):
    return DATA.get(name, [])


@pytest.fixture()
def qeng(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    return ResearchQueueEngine(ResearchAssistantEngine(reader=_reader))


def test_generate_produces_candidates(qeng):
    q = qeng.generate()
    assert q.proposal_count >= 1
    assert q.requires_human_approval is True


def test_unexplored_combination_present(qeng):
    q = qeng.generate(limit=20)
    combos = [p for p in q.proposals if p.kind == K_COMBINATION]
    assert combos, "미탐색 조합 제안이 있어야 한다"
    # insider 와 liquidity 는 개별 시도됐지만 함께는 아님 → 조합 후보
    names = " ".join(p.name.lower() for p in combos)
    assert "insider" in names or "liquidity" in names or "supply" in names


def test_failure_driven_proposal(qeng):
    q = qeng.generate(limit=20)
    fixes = [p for p in q.proposals if p.kind == K_FAILURE_FIX]
    assert fixes
    # 3건 실패 → 높은 신뢰도
    assert any(p.confidence == HIGH for p in fixes)


def test_event_driven_proposal(qeng):
    events = [{"name": "NVIDIA", "reason": "Taiwan shock", "confidence": "HIGH"}]
    q = qeng.generate(events=events, limit=20)
    evs = [p for p in q.proposals if p.kind == K_EVENT]
    assert evs
    assert evs[0].confidence == HIGH


def test_regime_driven_proposal(qeng):
    q = qeng.generate(regime="high volatility", limit=20)
    assert any(p.kind == "REGIME" for p in q.proposals)


def test_proposals_advisory(qeng):
    q = qeng.generate()
    for p in q.proposals:
        assert p.is_advisory is True and p.is_decision is False
        assert p.requires_human_approval is True


def test_deterministic(qeng):
    a = qeng.generate(limit=10).to_dict()
    b = qeng.generate(limit=10).to_dict()
    assert [p["proposal_id"] for p in a["proposals"]] == [p["proposal_id"] for p in b["proposals"]]


def test_record_proposals_writes_advisory_notes(qeng):
    q = qeng.generate(limit=5)
    recs = qeng.record_proposals(q, now="2026-01-01T00:00:00Z", commit=True)
    assert len(recs) == len(q.proposals)
    from jarvis.research_assistant import ledger as al
    assert len(al.read_notes()) == len(q.proposals)   # 기존 ras_ 원장 재사용(새 저장소 없음)


def test_record_proposals_notes_non_binding(qeng):
    q = qeng.generate(limit=3)
    recs = qeng.record_proposals(q, now="2026-01-01T00:00:00Z", commit=True)
    assert all(r["is_binding"] is False for r in recs)


def test_empty_memory_no_crash(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    q = ResearchQueueEngine(ResearchAssistantEngine(reader=lambda n: [])).generate()
    assert q.proposal_count == 0


# ── 안전 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "research_queue.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "research_queue.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_engine_no_execution_methods(qeng):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(qeng, m)


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "research_queue.py").read().lower()
