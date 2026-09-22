"""venue_risk.py — venue별 NAV 스냅샷/드로다운/자동킬 + firm-wide aggregate.
브로커 호출은 전부 monkeypatch, 파일 I/O는 tmp_path로 격리."""
from __future__ import annotations

import asyncio

from api_server import risk_state, venue_risk


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(venue_risk, "_DATA", tmp_path)
    monkeypatch.setattr(venue_risk, "_SNAPSHOT_PATH", tmp_path / "venue_risk_snapshots.jsonl")
    monkeypatch.setattr(risk_state, "_DATA", tmp_path)
    monkeypatch.setattr(risk_state, "_KILL", tmp_path / "risk_kill.json")


def _raise():
    raise RuntimeError("down")


async def _raise_async():
    raise RuntimeError("down")


def test_drawdown_pct_zero_on_first_observation(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert venue_risk.drawdown_pct("KR", 1000.0) == 0.0


def test_drawdown_pct_tracks_peak_across_history(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    venue_risk._append_snapshot("KR", 1000.0)
    venue_risk._append_snapshot("KR", 1200.0)
    dd = venue_risk.drawdown_pct("KR", 900.0)
    assert dd == round((900.0 - 1200.0) / 1200.0 * 100, 2)  # -25.0


def test_max_dd_limit_uses_venue_env_override(monkeypatch):
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_HL", "8")
    assert venue_risk.max_dd_limit("HL") == 8.0


def test_max_dd_limit_falls_back_to_shared_default(monkeypatch):
    monkeypatch.delenv("MAX_DRAWDOWN_PCT_KR", raising=False)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT", "20")
    assert venue_risk.max_dd_limit("KR") == 20.0


def test_check_and_kill_engages_when_breached(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_KR", "10")
    venue_risk._check_and_kill("KR", -15.0)
    assert risk_state.venue_engaged("KR") is True


def test_check_and_kill_is_sticky_once_engaged(tmp_path, monkeypatch):
    """이미 killed면 재호출 안 함 — 최초 원인이 다음 tick에서 덮어써지지 않아야 함."""
    _isolate(tmp_path, monkeypatch)
    risk_state.set_kill("KR", True, "최초 원인")
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_KR", "10")
    venue_risk._check_and_kill("KR", -50.0)
    state = risk_state._load()
    assert state["KR"]["reason"] == "최초 원인"


def test_tick_isolates_one_venue_failure(tmp_path, monkeypatch):
    """KR·US_IB 조회 실패해도 HL·US_ALPACA·aggregate는 정상 진행."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", _raise)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 500.0)
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 300.0)

    asyncio.run(venue_risk.tick())

    assert venue_risk.history("HL") == [500.0]
    assert venue_risk.history("KR") == []  # 실패한 venue는 스냅샷 기록 안 남음
    assert venue_risk.history("_AGGREGATE") == [800.0]  # HL 500 + US_ALPACA 300만


def test_tick_aggregate_reuses_last_known_value_on_fetch_failure(tmp_path, monkeypatch):
    """직전 tick 성공값이 있으면, 이번 tick 실패해도 그 값으로 aggregate에 포함."""
    _isolate(tmp_path, monkeypatch)
    venue_risk._append_snapshot("KR", 1000.0)  # 이전 tick의 성공 기록

    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", _raise)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 500.0)
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 300.0)

    asyncio.run(venue_risk.tick())

    assert venue_risk.history("_AGGREGATE") == [1800.0]  # KR 1000(재사용) + HL 500 + US_ALPACA 300


def test_tick_triggers_kill_when_venue_breaches_threshold(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_HL", "10")
    venue_risk._append_snapshot("HL", 1000.0)  # peak
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", lambda: 100.0)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 850.0)  # -15% > 10% 한도
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 100.0)

    asyncio.run(venue_risk.tick())

    assert risk_state.venue_engaged("HL") is True
    assert risk_state.venue_engaged("KR") is False  # 무관한 venue는 안 막힘
