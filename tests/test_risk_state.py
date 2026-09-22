"""Venue별 킬스위치 상태 저장/조회. 평가 로직(드로다운→자동킬)은 venue_risk.py —
여긴 상태 저장(risk_kill.json)과 is_killed() OR 판정만 담당."""
from __future__ import annotations

import json

from api_server import risk_state


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_state, "_DATA", tmp_path)
    monkeypatch.setattr(risk_state, "_KILL", tmp_path / "risk_kill.json")


def test_set_kill_and_is_killed_for_own_venue(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("KR", True, "테스트")
    assert risk_state.is_killed("KR") is True
    assert risk_state.is_killed("HL") is False


def test_is_killed_true_when_aggregate_engaged_even_if_own_venue_clean(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("_AGGREGATE", True, "전체 낙폭 초과")
    assert risk_state.is_killed("KR") is True
    assert risk_state.is_killed("HL") is True


def test_venue_engaged_ignores_aggregate(tmp_path, monkeypatch):
    """venue_engaged()는 sticky 자동킬 판정용 — _AGGREGATE OR 없이 자기 venue만 봄."""
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("_AGGREGATE", True, "전체 낙폭 초과")
    assert risk_state.venue_engaged("KR") is False
    assert risk_state.venue_engaged("_AGGREGATE") is True


def test_set_kill_preserves_other_venues(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("KR", True, "A")
    risk_state.set_kill("HL", True, "B")
    assert risk_state.is_killed("KR") is True
    assert risk_state.is_killed("HL") is True
    state = json.loads((tmp_path / "risk_kill.json").read_text())
    assert state["KR"]["reason"] == "A"
    assert state["HL"]["reason"] == "B"


def test_set_kill_can_disengage(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("KR", True, "A")
    risk_state.set_kill("KR", False, "manual")
    assert risk_state.is_killed("KR") is False


def test_old_single_dict_format_is_ignored_safely(tmp_path, monkeypatch):
    """구버전 risk_kill.json은 {"engaged":..., "reason":..., "ts":...} 단일 dict였음 —
    venue 키가 없으니 모든 venue engaged=False로 안전하게 취급돼야 함(예외 없이)."""
    kill_path = tmp_path / "risk_kill.json"
    kill_path.write_text(json.dumps({"engaged": True, "reason": "구버전", "ts": "2026-01-01"}))
    monkeypatch.setattr(risk_state, "_DATA", tmp_path)
    monkeypatch.setattr(risk_state, "_KILL", kill_path)
    assert risk_state.is_killed("KR") is False
    assert risk_state.is_killed("_AGGREGATE") is False


def test_missing_kill_file_defaults_to_not_killed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)  # 파일 자체가 없는 최초 실행 상태
    assert risk_state.is_killed("KR") is False
