"""인트라데이 저장소 테스트 (IB 무관, 순수)."""
from __future__ import annotations

import research.data.intraday_store as store


def _rows(base_ts: int, n: int, step: int = 900):
    return [
        {"ts_utc": base_ts + i * step, "open": 10.0 + i, "high": 11.0 + i,
         "low": 9.0 + i, "close": 10.5 + i, "volume": 100.0 + i}
        for i in range(n)
    ]


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    total = store.save_bars("TST", "15m", _rows(1_700_000_000, 5))
    assert total == 5
    df = store.load_df("TST", "15m")
    assert list(df.columns) == store.COLUMNS
    assert len(df) == 5
    assert df["ts_utc"].is_monotonic_increasing


def test_merge_dedup_on_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_bars("TST", "15m", _rows(1_700_000_000, 5))
    # 3개 겹치고 2개 새것 → 총 7 (중복 제거)
    total = store.save_bars("TST", "15m", _rows(1_700_000_000 + 2 * 900, 5))
    assert total == 7
    assert store.load_df("TST", "15m")["ts_utc"].is_unique


def test_latest_ts_for_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    assert store.latest_ts("TST", "15m") is None
    store.save_bars("TST", "15m", _rows(1_700_000_000, 4))
    assert store.latest_ts("TST", "15m") == 1_700_000_000 + 3 * 900


def test_quality_report_counts_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    rows = _rows(1_700_000_000, 3)
    # 세션 내 갭 하나 추가 (step*3 뒤)
    rows.append({"ts_utc": 1_700_000_000 + 6 * 900, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})
    store.save_bars("TST", "15m", rows)
    q = store.quality_report("TST", "15m")
    assert q["bars"] == 4
    assert q["duplicates"] == 0
    assert q["intraday_gaps"] >= 1


def test_load_ohlc_lists_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_bars("TST", "15m", _rows(1_700_000_000, 6))
    d = store.load_ohlc_lists("TST", "15m")
    assert len(d["close"]) == 6 and len(d["high"]) == 6
    assert all(isinstance(x, float) for x in d["close"])


def test_empty_load(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    assert len(store.load_df("NONE", "15m")) == 0
    assert store.quality_report("NONE", "15m")["bars"] == 0
