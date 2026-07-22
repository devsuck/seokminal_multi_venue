"""P7.2 Live Market Data Streaming 테스트.

deterministic replay · timestamp validation · stale · duplicate · quality flags ·
valuation compatibility · no execution capability · no permission escalation ·
append-only integrity · restart recovery.
"""
from __future__ import annotations

import os

import pytest

from jarvis.live_market_data.adapters import (
    IBStreamingProvider,
    KISStreamingProvider,
    MockStreamingProvider,
    simulate_ticks,
)
from jarvis.live_market_data.models import DUPLICATE, FUTURE, OK, STALE, SUSPECT


def _ticks():
    return {"AAA": [
        {"price": 100.0, "bid": 99.9, "ask": 100.1, "volume": 100, "timestamp": "2026-07-22T00:00:00Z"},
        {"price": 110.0, "bid": 109.9, "ask": 110.1, "volume": 120, "timestamp": "2026-07-22T00:00:10Z"},
        {"price": 121.0, "bid": 120.9, "ask": 121.1, "volume": 130, "timestamp": "2026-07-22T00:00:20Z"},
    ]}


# ── 1. deterministic tick replay ──
def test_deterministic_replay():
    a = MockStreamingProvider(_ticks(), clock="2026-07-22T00:00:25Z", stale_seconds=60)
    b = MockStreamingProvider(_ticks(), clock="2026-07-22T00:00:25Z", stale_seconds=60)
    assert a.latest("AAA").to_dict() == b.latest("AAA").to_dict()
    assert a.latest("AAA").price == 121.0
    # simulate_ticks도 결정적
    assert simulate_ticks(100, 5, "2026-07-22T00:00:00Z") == simulate_ticks(100, 5, "2026-07-22T00:00:00Z")


# ── 2. timestamp validation / no-lookahead ──
def test_timestamp_no_lookahead():
    # clock=00:00:12 → 00:00:20 틱(미래)을 안 봄 → 110
    p = MockStreamingProvider(_ticks(), clock="2026-07-22T00:00:12Z", stale_seconds=60)
    assert p.latest("AAA").price == 110.0


# ── 3. stale detection ──
def test_stale_detection():
    p = MockStreamingProvider(_ticks(), clock="2026-07-22T02:00:00Z", stale_seconds=60)
    assert p.latest("AAA").quality == STALE     # 최신 틱이 2시간 전


# ── 4. duplicate detection ──
def test_duplicate_detection():
    dup = {"AAA": [
        {"price": 100.0, "timestamp": "2026-07-22T00:00:00Z"},
        {"price": 100.0, "timestamp": "2026-07-22T00:00:00Z"},  # 동일 timestamp
    ]}
    p = MockStreamingProvider(dup, clock="2026-07-22T00:00:05Z", stale_seconds=3600)
    assert p.latest("AAA").quality == DUPLICATE


# ── 5. quality flags (jump / future / missing) ──
def test_quality_flags():
    # 이상 점프
    jump = {"AAA": [{"price": 100.0, "timestamp": "2026-07-22T00:00:00Z"},
                    {"price": 200.0, "timestamp": "2026-07-22T00:00:10Z"}]}  # +100%
    p = MockStreamingProvider(jump, clock="2026-07-22T00:00:11Z", stale_seconds=3600)
    assert p.latest("AAA").quality == SUSPECT
    # 미래 timestamp
    fut = {"AAA": [{"price": 100.0, "timestamp": "2026-07-30T00:00:00Z"}]}
    pf = MockStreamingProvider(fut, clock="2026-07-22T00:00:00Z")
    # clock 이하만 보므로 미래틱은 latest 후보에서 제외 → None
    assert pf.latest("AAA") is None
    # missing symbol
    assert MockStreamingProvider(_ticks()).latest("NOPE") is None


# ── 6. valuation compatibility (P6.3 무변경) ──
def test_valuation_compatibility():
    from jarvis.live_market_data.bridge import LiveToMarketDataAdapter, live_valuation_provider
    from jarvis.paper_execution.valuation import valuate
    live = MockStreamingProvider(_ticks(), clock="2026-07-22T00:00:25Z", stale_seconds=1e9)
    positions = [{"strategy_id": "AAA", "quantity": 10.0, "average_price": 100.0,
                  "market_value": 1000.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
                 {"strategy_id": "NODATA", "quantity": 5.0, "average_price": 50.0,
                  "market_value": 250.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0}]
    prov = live_valuation_provider(live, positions)     # 스트림 + flat-mark 폴백
    snap = valuate(positions, prov, capital=10000.0, now="2026-07-22T00:00:25Z")
    # AAA mark 121 → 10*(121-100)=210. NODATA flat-mark 50 → 0
    assert abs(snap.unrealized_pnl - 210.0) < 1e-6
    # .get 호환 확인
    assert LiveToMarketDataAdapter(live).get("AAA", "2026-07-22T00:00:25Z").price == 121.0


# ── 7. no execution capability ──
def test_no_execution_capability():
    for p in (MockStreamingProvider(_ticks()), IBStreamingProvider(), KISStreamingProvider()):
        for attr in ("execute", "place_order", "submit_order", "buy", "sell", "cancel_order"):
            assert not hasattr(p, attr)


def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "provider", "adapters", "bridge", "cache", "quality"):
        src = inspect.getsource(importlib.import_module(f"jarvis.live_market_data.{m}"))
        assert "jarvis.execution" not in src
        assert "jarvis.risk" not in src
        assert "jarvis.registry" not in src
        assert "place_order" not in src and "order_client" not in src


# ── 8. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("stream" in a or "live_market" in a for a in ACTION_PERMISSIONS)


# ── 9. append-only integrity (cache) ──
def test_append_only_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.live_market_data.cache.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.live_market_data.cache import read_ticks, record_tick
    p = MockStreamingProvider(_ticks(), clock="2026-07-22T00:00:25Z", stale_seconds=1e9)
    record_tick(p.latest("AAA"))
    record_tick(p.latest("AAA"))
    rows = read_ticks()
    assert len(rows) == 2 and all("hash" in r for r in rows)
    assert rows[0]["hash"] == rows[1]["hash"]           # 동일 틱 → 동일 해시(결정적)


# ── 10. restart recovery (cache replay) ──
def test_restart_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.live_market_data.cache.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.live_market_data.cache import CacheStreamingProvider, rebuild_index, record_tick
    live = MockStreamingProvider(_ticks(), clock="2026-07-22T00:00:25Z", stale_seconds=1e9)
    record_tick(live.latest("AAA"))
    # 재시작: 캐시 provider가 마지막 틱 복구
    restored = CacheStreamingProvider().latest("AAA")
    assert restored.price == 121.0
    assert rebuild_index() == rebuild_index()           # 결정적 재구축


# ── 미구성 플레이스홀더 ──
def test_placeholders_disconnected():
    for P in (IBStreamingProvider, KISStreamingProvider):
        h = P().health_check()
        assert h["connected"] is False and "not_configured" in h["error"]
        assert P().latest("AAA") is None
