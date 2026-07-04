"""ICT 프리미티브 정확성 테스트 — 알려진 패턴을 심고 탐지되는지.

탐지기가 객관적으로 맞아야 검증이 정직하다.
"""
from __future__ import annotations

import datetime as dt

from research.ict.primitives import (
    fair_value_gaps,
    in_killzone,
    in_ote,
    liquidity_sweeps,
    market_structure,
    order_blocks,
    ote_zone,
    swings,
)


def test_bullish_fvg_detected():
    # i-2 high=10, i low=11 → 갭 위 (bullish FVG at i=2)
    h = [10, 12, 13]
    l = [9, 10, 11]
    fv = fair_value_gaps(h, l)
    assert {"idx": 2, "type": "bullish", "gap_lo": 10, "gap_hi": 11} in fv


def test_bearish_fvg_detected():
    h = [20, 18, 15]   # i=2 high=15 < i0 low=19 → bearish
    l = [19, 16, 12]
    fv = fair_value_gaps(h, l)
    assert any(f["type"] == "bearish" and f["idx"] == 2 for f in fv)


def test_no_fvg_when_overlap():
    h = [10, 11, 12]
    l = [9, 9.5, 9.8]   # l[2]=9.8 < h[0]=10 → 갭 없음
    assert fair_value_gaps(h, l) == []


def test_bullish_order_block():
    # i=1 하락봉(c<o), i=2가 i=1 고가 돌파 → bullish OB at 1
    o = [10, 10.5, 10.0]
    c = [10.2, 10.0, 11.0]   # i1: c10.0<o10.5 하락, i2 c11.0>h1
    h = [10.3, 10.6, 11.1]
    l = [9.9, 9.8, 10.0]
    ob = order_blocks(o, h, l, c)
    assert any(b["idx"] == 1 and b["type"] == "bullish" for b in ob)


def test_bullish_liquidity_sweep():
    # 직전 최저 하회 후 회복
    h = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
    l = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 4]   # i=10 low=4 < prior min 5
    c = [6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6]   # 종가 6 > 5 회복
    sw = liquidity_sweeps(h, l, c, lookback=10)
    assert any(s["idx"] == 10 and s["type"] == "bullish" for s in sw)


def test_swings_fractal():
    h = [1, 2, 5, 2, 1]   # i=2 최고
    l = [5, 4, 1, 4, 5]   # i=2 최저
    sw = swings(h, l, k=2)
    assert 2 in sw["highs"] and 2 in sw["lows"]


def test_market_structure_bos():
    # 상승 swing high 만든 뒤 종가가 그 위 돌파 → bullish 이벤트
    h = [3, 5, 3, 3, 7]
    l = [1, 2, 1, 1, 4]
    c = [2, 4, 2, 2, 6.5]   # i=4 종가 6.5 > swing high(5) → 돌파
    ev = market_structure(h, l, c, k=1)
    assert any(e["dir"] == "bullish" for e in ev)


def test_killzone_utc_window():
    # 14:00 UTC = 킬존 안
    ts_in = int(dt.datetime(2024, 6, 3, 14, 0, tzinfo=dt.timezone.utc).timestamp())
    ts_out = int(dt.datetime(2024, 6, 3, 20, 0, tzinfo=dt.timezone.utc).timestamp())
    assert in_killzone(ts_in) is True
    assert in_killzone(ts_out) is False


def test_ote_zone():
    z = ote_zone(100.0, 200.0, "bullish")   # 62-79% 되돌림
    assert z[0] < z[1]
    assert in_ote(130.0, z) is True     # 130 = 70% 되돌림 근처
    assert in_ote(195.0, z) is False
