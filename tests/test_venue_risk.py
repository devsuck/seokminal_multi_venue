"""venue_risk.py — venue별 NAV 스냅샷/드로다운/자동킬 + firm-wide aggregate.
브로커 호출은 전부 monkeypatch, 파일 I/O는 tmp_path로 격리."""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging

import pytest

from api_server import risk_state, venue_risk
from jarvis.execution import broker_bridge


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


def test_drawdown_pct_is_current_from_peak_not_alltime_mdd(tmp_path, monkeypatch):
    """회귀: Fix 2 — history [1000, 700, 1500]에서 current=1500(역대 최고)은
    peak(자기 자신 포함) 대비 0.0이어야 함. 옛 all-time-MDD 방식은 -30.0을 반환했음
    (700에서의 옛 min() 낙폭이 새 관측 후에도 안 사라짐 — sticky kill이 회복 후에도
    안 풀리는 원인)."""
    _isolate(tmp_path, monkeypatch)
    venue_risk._append_snapshot("KR", 1000.0)
    venue_risk._append_snapshot("KR", 700.0)
    dd = venue_risk.drawdown_pct("KR", 1500.0)
    assert dd == 0.0


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
    venue_risk._append_snapshot("KR", 1000.0)  # 이전 tick의 성공 기록(KRW 네이티브)
    monkeypatch.setattr("jarvis.broker_readonly.aggregator._usdkrw_rate", lambda: 1.0)

    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", _raise)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 500.0)
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 300.0)

    asyncio.run(venue_risk.tick())

    assert venue_risk.history("_AGGREGATE") == [1800.0]  # KR 1000(재사용) + HL 500 + US_ALPACA 300


def test_kr_equity_native_returns_none_when_snapshot_equity_is_zero(monkeypatch):
    """회귀: Fix 1 — 조회 실패/0 잔고가 진짜 0 잔고와 구별 안 되면 0.0이 히스토리에
    쌓여서 -100% drawdown으로 오인되고 sticky kill이 걸림. 0 이하는 None이어야 함."""
    fake_snap = type("S", (), {"equity": 0.0})()
    monkeypatch.setattr(
        "jarvis.broker_readonly.live_providers.KISReadOnlyProvider.account_snapshot",
        lambda self: fake_snap,
    )
    assert venue_risk._kr_equity_native() is None


def test_hl_equity_usd_returns_none_when_snapshot_equity_is_zero(monkeypatch):
    fake_snap = type("S", (), {"equity": 0.0})()
    monkeypatch.setattr(
        "jarvis.broker_readonly.live_providers.HLReadOnlyProvider.account_snapshot",
        lambda self: fake_snap,
    )
    assert venue_risk._hl_equity_usd() is None


def test_us_ib_equity_usd_returns_none_when_net_liquidation_is_zero(monkeypatch):
    class _FakeIBClient:
        def __init__(self, *a, **kw):
            pass

        async def get_account_summary(self):
            return {"net_liquidation": 0.0}

    monkeypatch.setattr("backends.ib.client.IBClient", _FakeIBClient)
    assert asyncio.run(venue_risk._us_ib_equity_usd()) is None


def test_us_alpaca_equity_usd_returns_none_when_equity_is_zero(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")

    class _FakeAccount:
        equity = "0.0"

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_account(self):
            return _FakeAccount()

    monkeypatch.setattr("alpaca.trading.client.TradingClient", _FakeClient)
    assert venue_risk._us_alpaca_equity_usd() is None


def test_tick_triggers_kill_when_venue_breaches_threshold(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_HL", "10")
    venue_risk._append_snapshot("HL", 1000.0)  # peak
    monkeypatch.setattr("jarvis.broker_readonly.aggregator._usdkrw_rate", lambda: 1.0)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", lambda: 100.0)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 850.0)  # -15% > 10% 한도
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 100.0)

    asyncio.run(venue_risk.tick())

    assert risk_state.venue_engaged("HL") is True
    assert risk_state.venue_engaged("KR") is False  # 무관한 venue는 안 막힘


def test_tick_kill_is_persisted_to_real_file_and_blocks_broker_bridge(tmp_path, monkeypatch):
    """Fix 6 — 최종 리뷰가 지적한 통합 테스트 갭: is_killed()를 mock하지 않고 실제
    tmp-dir risk_kill.json 파일을 통해 venue_risk.tick() → risk_state.set_kill()
    → broker_bridge.route_order()의 _gate()까지 끝까지 통과시켜서, Fix 1의 버그
    (0.0이 실패로 오인되어 -100% drawdown 킬 유발)가 이번엔 이 경로에서 잡히는지
    확인한다."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_HL", "10")
    venue_risk._append_snapshot("HL", 1000.0)  # peak
    monkeypatch.setattr("jarvis.broker_readonly.aggregator._usdkrw_rate", lambda: 1.0)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", lambda: 100.0)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 850.0)  # -15% > 10% 한도
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 100.0)

    asyncio.run(venue_risk.tick())

    kill_file = tmp_path / "risk_kill.json"
    assert kill_file.exists()
    on_disk = json.loads(kill_file.read_text())
    assert on_disk["HL"]["engaged"] is True

    order = dict(venue="HL", symbol="BTC", side="BUY", quantity=0.001,
                 order_type="market", price=60000, paper=True)
    with pytest.raises(broker_bridge.BrokerOrderRejected, match="risk kill switch engaged"):
        broker_bridge.route_order(order)


def test_kr_kill_decision_uses_native_krw_not_fx_converted(tmp_path, monkeypatch):
    """Fix 8 — KR 자체 킬 판정은 KRW 원화 기준이어야 한다. FX가 급변(원화 반토막)해도
    원화 원금이 그대로면 KR 자체 dd는 0이어야 하고, 히스토리도 원화 그대로 쌓여야 함."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_KR", "10")
    venue_risk._append_snapshot("KR", 1_000_000.0)  # KRW peak
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", lambda: 1_000_000.0)  # 원화 그대로
    monkeypatch.setattr("jarvis.broker_readonly.aggregator._usdkrw_rate", lambda: 2000.0)  # FX만 급변
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 500.0)
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 300.0)

    asyncio.run(venue_risk.tick())

    assert risk_state.venue_engaged("KR") is False  # FX 급변에도 킬 안 걸림
    assert venue_risk.history("KR") == [1_000_000.0, 1_000_000.0]  # 원화 그대로 저장


def test_max_dd_limit_falls_back_when_venue_override_is_malformed(monkeypatch):
    monkeypatch.setenv("MAX_DRAWDOWN_PCT_KR", "abc")
    monkeypatch.setenv("MAX_DRAWDOWN_PCT", "20")
    assert venue_risk.max_dd_limit("KR") == 20.0


def test_max_dd_limit_falls_back_to_15_when_default_also_malformed(monkeypatch):
    monkeypatch.delenv("MAX_DRAWDOWN_PCT_KR", raising=False)
    monkeypatch.setenv("MAX_DRAWDOWN_PCT", "xyz")
    assert venue_risk.max_dd_limit("KR") == 15.0


def test_snapshot_file_is_pruned_when_it_exceeds_size_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(venue_risk, "_MAX_SNAPSHOT_BYTES", 200)
    for i in range(20):
        venue_risk._append_snapshot("KR", float(i))
    lines = venue_risk._SNAPSHOT_PATH.read_text().splitlines()
    assert len(lines) < 20  # 오래된 절반 버려짐
    assert json.loads(lines[-1])["equity_usd"] == 19.0  # 최신 값은 남아있음


def test_tick_logs_warning_when_reusing_stale_fallback_value(tmp_path, monkeypatch, caplog):
    """Fix 6 후속 — aggregate 계산은 안 바꾸되(false-kill 위험), stale 재사용은
    더 이상 silent하면 안 됨."""
    _isolate(tmp_path, monkeypatch)
    old_ts = (_dt.datetime.now(_dt.timezone.utc)
              - _dt.timedelta(seconds=venue_risk._STALE_AFTER_SEC + 1)).isoformat()
    venue_risk._SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with venue_risk._SNAPSHOT_PATH.open("w") as f:
        f.write(json.dumps({"ts": old_ts, "venue": "KR", "equity_usd": 1000.0}) + "\n")

    monkeypatch.setattr("jarvis.broker_readonly.aggregator._usdkrw_rate", lambda: 1.0)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "KR", _raise)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "HL", lambda: 500.0)
    monkeypatch.setattr(venue_risk, "_us_ib_equity_usd", _raise_async)
    monkeypatch.setitem(venue_risk._EQUITY_FETCHERS, "US_ALPACA", lambda: 300.0)

    with caplog.at_level(logging.WARNING):
        asyncio.run(venue_risk.tick())

    assert any("stale" in r.message for r in caplog.records)
    assert venue_risk.history("_AGGREGATE") == [1800.0]  # 동작 자체는 안 바뀜 — 여전히 재사용
