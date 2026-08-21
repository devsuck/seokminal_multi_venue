"""OI 저장소 테스트 (HL 무관, 순수)."""
from __future__ import annotations

import research.data.oi_store as store


def _rows(base_ts: int, n: int, step: int = 3600):
    return [{"ts": base_ts + i * step, "open_interest": 1000.0 + i, "mark_px": 50000.0 + i} for i in range(n)]


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    total = store.save_oi("BTC", _rows(1_700_000_000, 5))
    assert total == 5
    df = store.load_df("BTC")
    assert list(df.columns) == store.COLUMNS
    assert len(df) == 5
    assert df["ts"].is_monotonic_increasing


def test_merge_dedup_on_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_oi("BTC", _rows(1_700_000_000, 5))
    total = store.save_oi("BTC", _rows(1_700_000_000 + 2 * 3600, 5))
    assert total == 7
    assert store.load_df("BTC")["ts"].is_unique


def test_latest_ts_for_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    assert store.latest_ts("BTC") is None
    store.save_oi("BTC", _rows(1_700_000_000, 4))
    assert store.latest_ts("BTC") == 1_700_000_000 + 3 * 3600


def test_quality_report_counts_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    rows = _rows(1_700_000_000, 3)
    rows.append({"ts": 1_700_000_000 + 6 * 3600, "open_interest": 1, "mark_px": 1})
    store.save_oi("BTC", rows)
    q = store.quality_report("BTC")
    assert q["records"] == 4
    assert q["duplicates"] == 0
    assert q["gaps_gt_1h"] >= 1


def test_load_series_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_oi("BTC", _rows(1_700_000_000, 6))
    d = store.load_series("BTC")
    assert len(d["time"]) == 6 and len(d["open_interest"]) == 6
    assert all(isinstance(x, float) for x in d["mark_px"])
