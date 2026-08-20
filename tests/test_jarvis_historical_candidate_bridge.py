"""jarvis.research_workflow.historical_candidate_bridge — recall_first → research_strategy_generation
(P29) 원장 로깅 부활 확인. mode="historical" 이 research_discovery.generate() 로 조율되는지도 검증.
"""
from __future__ import annotations

from jarvis.research_strategy_generation import ledger as rsg_ledger
from jarvis.research_workflow import historical_candidate_bridge as bridge
from jarvis.research_workflow import research_discovery as rd


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.research_strategy_generation.ledger.state_path",
                        lambda name: str(tmp_path / name))


def test_bridge_propose_logs_real_ledger_events(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    out = bridge.propose("momentum KR", limit=3)
    assert out["mode"] == "historical" and out["is_decision"] is False
    assert out["count"] >= 1
    assert len(rsg_ledger.read_session_events()) >= 1
    assert len(rsg_ledger.read_candidate_events()) == out["count"]
    assert all(ev["is_selected"] is False for ev in rsg_ledger.read_candidate_events())


def test_research_discovery_dispatches_historical_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    g = rd.generate("momentum KR", limit=3, mode="historical")
    assert g["mode"] == "historical"
    # 다른 3 모드와 동일 shape(생성 파사드 계약)
    other = rd.generate("momentum KR", limit=3, mode="template")
    assert set(g) == set(other)


def test_no_new_ledger_created():
    # P29 는 기존 rsg_ 원장 7개만 사용 — 새 지식 저장소 없음
    assert len(rsg_ledger.ALL_LEDGERS) == 7
    for fname, _ in rsg_ledger.ALL_LEDGERS:
        assert fname.startswith("rsg_")
