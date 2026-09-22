"""Venue별 킬스위치 상태 저장/조회. 평가 로직(드로다운→자동킬)은 venue_risk.py —
여긴 상태 저장(risk_kill.json)과 is_killed() OR 판정만 담당."""
from __future__ import annotations

import json

from api_server import risk_state, venue_risk


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_state, "_DATA", tmp_path)
    monkeypatch.setattr(risk_state, "_KILL", tmp_path / "risk_kill.json")
    monkeypatch.setattr(venue_risk, "_DATA", tmp_path)
    monkeypatch.setattr(venue_risk, "_SNAPSHOT_PATH", tmp_path / "venue_risk_snapshots.jsonl")


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


def test_set_kill_does_not_leave_tmp_file_behind(tmp_path, monkeypatch):
    """Fix 4 — atomic replace: .tmp가 write 후 남아있으면 안 됨."""
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("KR", True, "A")
    assert not (tmp_path / "risk_kill.json.tmp").exists()
    assert (tmp_path / "risk_kill.json").exists()


def test_risk_status_compat_fields_reflect_any_venue_killed(tmp_path, monkeypatch):
    """Fix 3 회귀 — GET /risk/status 응답의 top-level compat 필드(kill_engaged 등)는
    _AGGREGATE 하나만 보는 게 아니라 any(venue killed)를 반영해야 함(옛 대시보드
    비상정지 위젯이 개별 venue 킬에도 정상적으로 반응해야 함)."""
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("HL", True, "HL만 킬됨")

    status = risk_state.risk_status()

    assert status.kill_engaged is True
    assert status.kill_reason == "HL만 킬됨"
    assert status.drawdown_breached is True


def test_risk_status_compat_fields_false_when_nothing_killed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    status = risk_state.risk_status()
    assert status.kill_engaged is False
    assert status.kill_reason == ""
    assert status.drawdown_breached is False


def test_risk_kill_old_two_field_body_defaults_to_aggregate(tmp_path, monkeypatch):
    """Fix 3 회귀 — venue 없는 옛 2-필드 POST 바디는 _AGGREGATE를 킬해야 하고,
    is_killed()의 OR 판정으로 모든 venue가 막혀야 함(옛 단일 전역 킬스위치와
    동등한 효과)."""
    _isolate(tmp_path, monkeypatch)
    body = risk_state.KillRequest(engaged=True, reason="x")  # venue 필드 없이 생성 — 옛 바디와 동일
    assert body.venue == "_AGGREGATE"

    result = risk_state.risk_kill(body)

    assert result["venue"] == "_AGGREGATE"
    assert risk_state.is_killed("KR") is True
    assert risk_state.is_killed("HL") is True
    assert risk_state.is_killed("_AGGREGATE") is True
