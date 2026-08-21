"""청산 수집기 저장 로직 테스트 — 네트워크 없이 fake client로 flush 동작만 검증."""
from __future__ import annotations

import itertools

from orderflow.models import LiquidationEvent
from research.run_liquidation_collect import run_coin_forever


class _FakeClient:
    def __init__(self, events):
        self._events = events

    async def stream_liquidations(self, coin):
        for e in self._events:
            yield e


def _event(ts, side, size, price):
    return LiquidationEvent(symbol="BTC", ts=ts, price=price, size=size, side=side)


async def test_flushes_on_stream_end():
    events = [_event(1_700_000_000, "long", 1.5, 50000.0), _event(1_700_000_001, "short", 2.0, 50010.0)]
    saved = []
    await run_coin_forever(
        "BTC", client=_FakeClient(events), save_fn=lambda coin, rows: saved.append((coin, rows)),
        max_cycles=1,
    )
    assert len(saved) == 1
    coin, rows = saved[0]
    assert coin == "BTC"
    assert rows == [
        {"ts": 1_700_000_000, "side": "long", "qty": 1.5, "price": 50000.0, "venue": "binance"},
        {"ts": 1_700_000_001, "side": "short", "qty": 2.0, "price": 50010.0, "venue": "binance"},
    ]


async def test_flushes_mid_stream_on_interval(monkeypatch):
    events = [_event(1_700_000_000, "long", 1.0, 50000.0), _event(1_700_000_001, "short", 1.0, 50010.0)]
    ticks = iter([0.0, 100.0, 100.0])  # 첫 이벤트 후 100초 경과한 것처럼(FLUSH 간격 30s 초과)
    saved = []
    await run_coin_forever(
        "BTC", client=_FakeClient(events), save_fn=lambda coin, rows: saved.append((coin, rows)),
        now_fn=lambda: next(ticks), flush_interval_s=30.0, max_cycles=1,
    )
    assert len(saved) >= 1
    assert saved[0][1][0]["ts"] == 1_700_000_000
