"""Basis 수집기 저장 로직 테스트 — HL client + Binance REST fake, 네트워크 없음, 실제 data/basis/ 미접근."""
from __future__ import annotations

import research.data.basis_store as basis_store
import research.run_basis_collect as run_basis_collect


def _fake_meta_and_ctxs():
    universe = [{"name": "BTC"}, {"name": "ETH"}, {"name": "DOGE"}]
    ctxs = [{"markPx": "100.5"}, {"markPx": "3000.0"}, {"markPx": "0.1"}]
    return universe, ctxs


def _fake_spot_px(coin):
    return {"BTC": 100.0, "ETH": 3003.0}[coin]


def test_collect_computes_basis_bps(tmp_path, monkeypatch):
    monkeypatch.setattr(basis_store, "STORE_DIR", str(tmp_path))
    monkeypatch.setattr(run_basis_collect, "get_meta_and_ctxs", _fake_meta_and_ctxs)
    monkeypatch.setattr(run_basis_collect, "_spot_px", _fake_spot_px)

    saved = run_basis_collect.collect(["BTC", "ETH"], now=1_700_000_000)

    assert saved == {"BTC": 1, "ETH": 1}
    series = basis_store.load_series("BTC")
    assert series["time"] == [1_700_000_000]
    assert series["spot_px"] == [100.0]
    assert series["perp_px"] == [100.5]
    assert series["basis_bps"] == [50.0]  # (100.5 - 100.0) / 100.0 * 10000


def test_coin_outside_binance_map_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(basis_store, "STORE_DIR", str(tmp_path))
    monkeypatch.setattr(run_basis_collect, "get_meta_and_ctxs", _fake_meta_and_ctxs)
    monkeypatch.setattr(run_basis_collect, "_spot_px", _fake_spot_px)

    saved = run_basis_collect.collect(["DOGE"], now=1_700_000_000)

    assert saved == {}
    assert basis_store.load_df("DOGE").empty


def test_default_coins_uses_binance_symbol_map_and_skips_missing_perp(tmp_path, monkeypatch):
    monkeypatch.setattr(basis_store, "STORE_DIR", str(tmp_path))
    monkeypatch.setattr(run_basis_collect, "get_meta_and_ctxs", _fake_meta_and_ctxs)
    monkeypatch.setattr(run_basis_collect, "_spot_px", _fake_spot_px)

    saved = run_basis_collect.collect(None, now=1_700_000_000)

    # BINANCE_SYMBOL_MAP = BTC/ETH/SOL, SOL has no perp_px in fake ctxs -> skipped
    assert set(saved.keys()) == {"BTC", "ETH"}
