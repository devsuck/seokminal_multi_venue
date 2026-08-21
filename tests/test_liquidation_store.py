"""청산 저장소 테스트 (Binance 무관, 순수)."""
from __future__ import annotations

import research.data.liquidation_store as store


def _rows(base_ts: int, n: int, step: int = 5):
    return [
        {"ts": base_ts + i * step, "side": "long" if i % 2 == 0 else "short",
         "qty": 1.0 + i, "price": 50000.0 + i, "venue": "binance"}
        for i in range(n)
    ]


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    total = store.save_liquidations("BTC", _rows(1_700_000_000, 5))
    assert total == 5
    df = store.load_df("BTC")
    assert list(df.columns) == store.COLUMNS
    assert len(df) == 5
    assert df["ts"].is_monotonic_increasing


def test_merge_dedup_on_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_liquidations("BTC", _rows(1_700_000_000, 5))
    # 완전히 동일한 이벤트 재전송 — 전부 dedup 대상
    total = store.save_liquidations("BTC", _rows(1_700_000_000, 5))
    assert total == 5


def test_merge_appends_new_events(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_liquidations("BTC", _rows(1_700_000_000, 5))
    total = store.save_liquidations("BTC", _rows(1_700_000_000 + 100, 3))
    assert total == 8


def test_quality_report_counts_sides(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_liquidations("BTC", _rows(1_700_000_000, 4))
    q = store.quality_report("BTC")
    assert q["records"] == 4
    assert q["long_count"] == 2
    assert q["short_count"] == 2


def test_load_series_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    store.save_liquidations("BTC", _rows(1_700_000_000, 3))
    d = store.load_series("BTC")
    assert len(d["time"]) == 3 and len(d["side"]) == 3
    assert all(isinstance(x, float) for x in d["price"])
