"""historical_candidate_bridge(research_workflow) → research_strategy_generation(P29) 원장 로깅 테스트.

recall_first 후보를 statement 로 정리해 rsg_ 원장에 append-only 로 기록하는지 검증(부활 확인)."""
from __future__ import annotations

from jarvis.research_strategy_generation import ledger
from jarvis.research_workflow import historical_candidate_bridge as bridge


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.research_strategy_generation.ledger.state_path",
                        lambda name: str(tmp_path / name))


def test_propose_logs_session_and_candidates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    out = bridge.propose("momentum KR", limit=3)
    assert out["stage"] == "generate" and out["mode"] == "historical"
    assert out["is_decision"] is False
    assert out["count"] >= 1
    assert len(ledger.read_session_events()) >= 1
    assert len(ledger.read_candidate_events()) == out["count"]


def test_propose_candidates_never_selected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    bridge.propose("momentum KR", limit=2)
    assert all(ev["is_selected"] is False for ev in ledger.read_candidate_events())


def test_propose_source_refs_from_recall_first(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    bridge.propose("momentum KR", limit=2)
    for ev in ledger.read_candidate_events():
        assert ev["source_refs"]  # recall_first 근거(hypothesis_id/evidence) 포함


def test_propose_idempotent_no_duplicate_candidates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = bridge.propose("momentum KR", limit=2)
    n_after_first = len(ledger.read_candidate_events())
    b = bridge.propose("momentum KR", limit=2)
    assert len(ledger.read_candidate_events()) == n_after_first  # append-only, 재기록 없음
    assert {c["candidate_id"] for c in a["hypotheses"]} == {c["candidate_id"] for c in b["hypotheses"]}


def test_propose_no_new_ledger():
    assert len(ledger.ALL_LEDGERS) == 7  # 새 원장 없음, 기존 rsg_ 원장에만 씀
