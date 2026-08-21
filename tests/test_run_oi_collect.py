"""OI 수집기 저장 로직 테스트 — HL client fake, 네트워크 없음, 실제 data/oi/ 미접근."""
from __future__ import annotations

import time

import research.data.oi_store as oi_store
import research.run_oi_collect as run_oi_collect


def _fake_meta_and_ctxs():
    universe = [{"name": "BTC"}, {"name": "ETH"}, {"name": "DOGE"}]
    ctxs = [
        {"openInterest": "1234.5", "markPx": "50000.0"},
        {"openInterest": "999.0", "markPx": "3000.0"},
        {"openInterest": "1.0", "markPx": "0.1"},
    ]
    return universe, ctxs


def test_collect_saves_all_wanted_coins(tmp_path, monkeypatch):
    monkeypatch.setattr(oi_store, "STORE_DIR", str(tmp_path))
    monkeypatch.setattr(run_oi_collect, "get_meta_and_ctxs", _fake_meta_and_ctxs)
    monkeypatch.setattr(run_oi_collect, "LIQUID_PERPS", ["BTC", "ETH", "DOGE"])

    saved = run_oi_collect.collect(None, now=1_700_000_000)

    assert saved == {"BTC": 1, "ETH": 1, "DOGE": 1}
    series = oi_store.load_series("BTC")
    assert series["time"] == [1_700_000_000]
    assert series["open_interest"] == [1234.5]
    assert series["mark_px"] == [50000.0]


def test_coins_filter_restricts_to_specified(tmp_path, monkeypatch):
    monkeypatch.setattr(oi_store, "STORE_DIR", str(tmp_path))
    monkeypatch.setattr(run_oi_collect, "get_meta_and_ctxs", _fake_meta_and_ctxs)

    saved = run_oi_collect.collect(["BTC"], now=1_700_000_000)

    assert saved == {"BTC": 1}
    assert oi_store.load_df("ETH").empty


def test_now_defaults_to_current_time(tmp_path, monkeypatch):
    monkeypatch.setattr(oi_store, "STORE_DIR", str(tmp_path))
    monkeypatch.setattr(run_oi_collect, "get_meta_and_ctxs", _fake_meta_and_ctxs)

    before = int(time.time())
    run_oi_collect.collect(["BTC"])
    after = int(time.time())

    ts = oi_store.load_series("BTC")["time"][0]
    assert before <= ts <= after
