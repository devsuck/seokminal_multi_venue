import json

import pandas as pd
import pytest

import research.hypotheses.cross_venue_skew as cvs
from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_price_series,
    load_venue_snapshots,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_load_venue_snapshots_reads_and_sorts_by_ts(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
        {"ts": 1.0, "bids": [{"price": 98.0, "size": 2.0}], "asks": [{"price": 102.0, "size": 2.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_venue_snapshots_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 1.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    _write_jsonl(tmp_path / "binance_BTC_2026-07-13.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12", "2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_venue_snapshots_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    df = load_venue_snapshots("binance", "BTC", ["2026-01-01"])
    assert df.empty


def test_build_imbalance_neutral_when_bid_ask_equal():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 5.0}]],
        "asks": [[{"price": 101.0, "size": 5.0}]],
    })
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.5)


def test_build_imbalance_buy_heavy_above_half():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 8.0}]],
        "asks": [[{"price": 101.0, "size": 2.0}]],
    })
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.8)


def test_build_imbalance_respects_depth_n():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 1.0}, {"price": 98.0, "size": 100.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}]],
    })
    result = build_imbalance(df, depth_n=1)
    assert result.iloc[0] == pytest.approx(0.5)  # depth=1이면 size=100 레벨 무시


def test_build_imbalance_empty_book_returns_neutral():
    df = pd.DataFrame({"ts": [1.0], "bids": [[]], "asks": [[]]})
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.5)


def test_build_imbalance_index_is_ts():
    df = pd.DataFrame({
        "ts": [1.0, 2.0],
        "bids": [[{"price": 99.0, "size": 1.0}], [{"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}], [{"price": 101.0, "size": 1.0}]],
    })
    result = build_imbalance(df)
    assert list(result.index) == [1.0, 2.0]


def test_align_venues_forward_fills_within_tolerance():
    a = pd.Series([0.6, 0.7], index=[1.0, 20.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert aligned.loc[2.0, "a"] == pytest.approx(0.6)
    assert aligned.loc[4.0, "b"] == pytest.approx(0.4)  # gap=3s, 5s 이내


def test_align_venues_nan_when_gap_exceeds_tolerance():
    a = pd.Series([0.6, 0.65], index=[1.0, 20.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert pd.isna(aligned.loc[9.0, "b"])  # gap=8s, 5s 초과


def test_align_venues_columns_are_venue_names():
    a = pd.Series([0.6], index=[1.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert set(aligned.columns) == {"a", "b"}


def test_build_price_series_averages_venue_mids():
    venue_a = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}]],
    })  # mid = 100.0
    venue_b = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 98.0, "size": 1.0}]],
        "asks": [[{"price": 102.0, "size": 1.0}]],
    })  # mid = 100.0
    price = build_price_series({"a": venue_a, "b": venue_b})
    assert price.loc[1.0] == pytest.approx(100.0)


def test_build_price_series_uses_max_bid_min_ask_not_list_order():
    venue_a = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 90.0, "size": 1.0}, {"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 105.0, "size": 1.0}, {"price": 101.0, "size": 1.0}]],
    })
    price = build_price_series({"a": venue_a})
    # correct mid = (max(90,99)=99 + min(105,101)=101)/2 = 100.0
    # naive first-element mid = (90+105)/2 = 97.5 (differs, so this discriminates)
    assert price.loc[1.0] == pytest.approx(100.0)
