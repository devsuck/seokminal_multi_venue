"""P6.4 Market Data Feed 테스트.

provider interface · CSV loading · timestamp validation · stale · missing · duplicate ·
cache rebuild · determinism · no execution capability · paper valuation integration.
"""
from __future__ import annotations

import os

import pytest

from jarvis.market_data.adapters import CSVHistoricalProvider, PublicAPIProvider
from jarvis.market_data.models import MISSING, OK, STALE
from jarvis.market_data.quality import assess_series


def _rows():
    return [
        {"symbol": "AAA", "timestamp": "2026-07-20T00:00:00Z", "price": "100"},
        {"symbol": "AAA", "timestamp": "2026-07-21T00:00:00Z", "price": "110"},
        {"symbol": "AAA", "timestamp": "2026-07-22T00:00:00Z", "price": "121"},
        {"symbol": "BBB", "timestamp": "2026-07-22T00:00:00Z", "close": "50"},   # OHLCV close
    ]


# ── 1. provider interface ──
def test_provider_interface():
    p = CSVHistoricalProvider(rows=_rows())
    # get_price / get_snapshot / health_check + P6.3 .get 별칭
    snap = p.get_price("AAA", "2026-07-22T12:00:00Z")
    assert snap.symbol == "AAA" and snap.source == "csv"
    assert p.get("AAA", "2026-07-22T12:00:00Z").price == snap.price   # .get 호환
    snaps = p.get_snapshot(["AAA", "BBB"], "2026-07-22T12:00:00Z")
    assert set(snaps) == {"AAA", "BBB"}
    assert p.health_check()["status"] == "ok"


# ── 2. CSV loading (파일) ──
def test_csv_loading(tmp_path):
    csv_path = tmp_path / "px.csv"
    csv_path.write_text("symbol,timestamp,price\nAAA,2026-07-22T00:00:00Z,101\n")
    p = CSVHistoricalProvider(str(csv_path))
    assert p.get_price("AAA").price == 101.0
    assert p.health_check()["n_rows"] == 1


def test_ohlcv_close_used_as_price():
    p = CSVHistoricalProvider(rows=_rows())
    assert p.get_price("BBB").price == 50.0


# ── 3. timestamp validation / no-lookahead ──
def test_timestamp_validation_and_no_lookahead():
    p = CSVHistoricalProvider(rows=_rows())
    # as-of 07-21 → 미래(07-22 121)를 안 봄 → 110
    assert p.get_price("AAA", "2026-07-21T12:00:00Z").price == 110.0
    # 잘못된 timestamp → 무시(invalid 카운트)
    bad = CSVHistoricalProvider(rows=[{"symbol": "X", "timestamp": "not-a-date", "price": "1"}])
    assert bad.get_price("X") is None and bad.health_check()["invalid_rows"] == 1


# ── 4. stale detection ──
def test_stale_detection():
    p = CSVHistoricalProvider(rows=[{"symbol": "S", "timestamp": "2026-07-01T00:00:00Z", "price": "9"}],
                              stale_hours=24)
    snap = p.get_price("S", "2026-07-22T00:00:00Z")     # 3주 전 → STALE
    assert snap.quality == STALE and snap.price == 9.0


# ── 5. missing price handling ──
def test_missing_price():
    p = CSVHistoricalProvider(rows=_rows())
    assert p.get_price("NOPE", "2026-07-22T00:00:00Z") is None
    assert p.get_snapshot(["NOPE"], "t")["NOPE"] is None


# ── 6. duplicate / future / jump (quality) ──
def test_quality_duplicate_future_jump():
    bars = [("2026-07-20T00:00:00Z", 100.0), ("2026-07-20T00:00:00Z", 100.0),  # dup
            ("2026-07-21T00:00:00Z", 300.0),                                    # +200% jump
            ("2026-07-30T00:00:00Z", 305.0)]                                    # 미래(now=22)
    rep = assess_series("Z", bars, "2026-07-22T00:00:00Z", stale_hours=48, jump_pct=0.5)
    kinds = {i["type"] for i in rep.issues}
    assert "duplicate_timestamp" in kinds
    assert "future_timestamp" in kinds
    assert "abnormal_jump" in kinds
    assert rep.quality_score < 1.0


def test_quality_missing_series():
    rep = assess_series("Z", [], "2026-07-22T00:00:00Z")
    assert rep.n_bars == 0 and rep.quality_score == 0.0


# ── 7. cache rebuild ──
def test_cache_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.market_data.cache.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.market_data.cache import CacheProvider, cache_snapshot, latest_from_cache, rebuild_index
    from jarvis.market_data.models import PriceSnapshot
    cache_snapshot(PriceSnapshot("AAA", 100.0, "2026-07-21T00:00:00Z", "csv"))
    cache_snapshot(PriceSnapshot("AAA", 110.0, "2026-07-22T00:00:00Z", "csv"))   # 최신
    assert latest_from_cache()["AAA"]["price"] == 110.0
    assert CacheProvider().get_price("AAA", "2026-07-22T12:00:00Z").price == 110.0
    assert rebuild_index() == rebuild_index()           # 결정적


# ── 8. deterministic output ──
def test_deterministic_output():
    p1 = CSVHistoricalProvider(rows=_rows())
    p2 = CSVHistoricalProvider(rows=_rows())
    assert p1.get_price("AAA", "2026-07-22T12:00:00Z").to_dict() == \
           p2.get_price("AAA", "2026-07-22T12:00:00Z").to_dict()


# ── 9. no execution capability ──
def test_no_execution_capability():
    p = CSVHistoricalProvider(rows=_rows())
    # 주문/체결 메서드 없음
    for attr in ("execute", "place_order", "submit_order", "buy", "sell"):
        assert not hasattr(p, attr)
    # 추상 API도 자격증명/네트워크 없음
    api = PublicAPIProvider()
    assert api.get_price("X") is None and api.health_check()["status"] == "abstract"


# ── 10. paper valuation integration (drop-in) ──
def test_paper_valuation_integration():
    from jarvis.market_data.bridge import paper_valuation_provider
    from jarvis.paper_execution.valuation import valuate
    positions = [{"strategy_id": "AAA", "quantity": 10.0, "average_price": 100.0,
                  "market_value": 1000.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
                 {"strategy_id": "NODATA", "quantity": 5.0, "average_price": 200.0,
                  "market_value": 1000.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0}]
    primary = CSVHistoricalProvider(rows=_rows())          # AAA=121 @07-22, NODATA 없음
    prov = paper_valuation_provider(primary, positions)     # 실데이터+flat-mark 폴백
    snap = valuate(positions, prov, capital=10000.0, now="2026-07-22T12:00:00Z")
    # AAA 미실현 = 10*(121-100)=210, NODATA는 flat-mark(200)→0
    assert abs(snap.unrealized_pnl - 210.0) < 1e-6
    assert "NODATA" not in snap.stale_symbols               # 폴백이 값 제공(None 아님)


# ── no source mutation (read-only 어댑터) ──
def test_csv_provider_no_side_effects(tmp_path):
    csv_path = tmp_path / "px.csv"
    content = "symbol,timestamp,price\nAAA,2026-07-22T00:00:00Z,101\n"
    csv_path.write_text(content)
    CSVHistoricalProvider(str(csv_path)).get_price("AAA")
    assert csv_path.read_text() == content                 # CSV 불변
