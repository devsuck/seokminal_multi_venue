import json

import pandas as pd
import pytest

import research.hypotheses.polymarket_whale as pw
from research.hypotheses.polymarket_whale import (
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _row(cid="c1", ts=1.0, side="BUY", price=0.5, size=100.0, family="news"):
    return {"conditionId": cid, "timestamp": ts, "side": side, "price": price,
            "size": size, "family": family, "transactionHash": f"tx{ts}"}


def test_load_whale_trades_reads_and_computes_notional(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-13.jsonl", [_row(ts=2.0, price=0.5, size=100.0),
                                                  _row(ts=1.0, price=0.4, size=50.0)])
    df = load_whale_trades(["2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]
    assert df.iloc[0]["notional_usd"] == pytest.approx(20.0)
    assert df.iloc[1]["notional_usd"] == pytest.approx(50.0)


def test_load_whale_trades_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-12.jsonl", [_row(ts=1.0)])
    _write_jsonl(tmp_path / "2026-07-13.jsonl", [_row(ts=2.0)])
    df = load_whale_trades(["2026-07-12", "2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_whale_trades_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "_DATA_DIR", tmp_path)
    df = load_whale_trades(["2020-01-01"])
    assert df.empty


def test_build_notional_zscore_nan_before_warmup():
    rows = [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
              "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(10)]
    df = pd.DataFrame(rows)
    out = build_notional_zscore(df)
    assert out["notional_z"].isna().all()  # WARMUP=20 미달


def test_build_notional_zscore_flags_spike_after_warmup():
    rows = [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
              "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(25)]
    rows.append({"ts": 25.0, "condition_id": "c1", "side": "BUY", "price": 0.5,
                  "size": 2000.0, "notional_usd": 1000.0, "family": "news"})
    df = pd.DataFrame(rows)
    out = build_notional_zscore(df)
    last_z = out.iloc[-1]["notional_z"]
    assert last_z > pw.WHALE_ZSCORE_THRESHOLD


def test_build_notional_zscore_groups_by_condition_id_independently():
    rows = (
        [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
          "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(25)]
        + [{"ts": float(i), "condition_id": "c2", "side": "BUY", "price": 0.5,
            "size": 500.0, "notional_usd": 250.0, "family": "sports"} for i in range(25)]
    )
    df = pd.DataFrame(rows)
    out = build_notional_zscore(df)
    c2_z = out[out["condition_id"] == "c2"]["notional_z"]
    assert (c2_z.dropna().abs() < 1e-6).all()  # c2는 전부 동일값 -> std=0 -> NaN 처리


def test_build_spike_signal_filters_by_threshold_and_sets_direction():
    df = pd.DataFrame([
        {"ts": 1.0, "condition_id": "c1", "side": "BUY", "notional_usd": 100.0,
         "notional_z": 2.5, "family": "news"},
        {"ts": 2.0, "condition_id": "c1", "side": "SELL", "notional_usd": 50.0,
         "notional_z": 1.0, "family": "news"},
        {"ts": 3.0, "condition_id": "c1", "side": "SELL", "notional_usd": 90.0,
         "notional_z": -2.1, "family": "news"},
    ])
    spikes = build_spike_signal(df)
    assert list(spikes["ts"]) == [1.0, 3.0]
    assert spikes.iloc[0]["direction"] == 1.0
    assert spikes.iloc[1]["direction"] == -1.0


def test_build_price_series_ffill_grid():
    df = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "price": 0.5},
        {"ts": 12.0, "condition_id": "c1", "price": 0.6},
    ])
    series = build_price_series(df, "c1")
    assert series.loc[0.0] == pytest.approx(0.5)
    assert series.loc[5.0] == pytest.approx(0.5)
    assert series.loc[10.0] == pytest.approx(0.5)
    assert series.loc[15.0] == pytest.approx(0.6)


def test_build_labels_multi_horizon_computes_forward_return():
    price = pd.Series([0.5, 0.5, 0.6, 0.6, 0.7, 0.7, 0.7],
                       index=[0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    spikes = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "family": "news", "side": "BUY",
         "direction": 1.0, "notional_usd": 100.0, "notional_z": 2.5},
    ])
    labels = build_labels_multi_horizon({"c1": price}, spikes, horizons_s=[10, 30])
    row10 = labels[labels["horizon_s"] == 10].iloc[0]
    assert row10["forward_return"] == pytest.approx((0.6 - 0.5) / 0.5)
    row30 = labels[labels["horizon_s"] == 30].iloc[0]
    assert row30["forward_return"] == pytest.approx((0.7 - 0.5) / 0.5)


def test_build_labels_multi_horizon_excludes_missing_condition():
    price = pd.Series([0.5], index=[0.0])
    spikes = pd.DataFrame([
        {"ts": 0.0, "condition_id": "unknown", "family": "news", "side": "BUY",
         "direction": 1.0, "notional_usd": 100.0, "notional_z": 2.5},
    ])
    labels = build_labels_multi_horizon({"c1": price}, spikes, horizons_s=[10])
    assert labels.empty
