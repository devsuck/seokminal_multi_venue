from research.hypotheses.orderflow_context_gate import (
    build_key_level_filter,
    build_ohlc_bars,
    build_trend_filter,
    resample_bars,
)


def _tick(ts, price, size=1.0, side="buy"):
    return {"ts": ts, "price": price, "size": size, "side": side}


def _bar(ts, o, h, l, c):
    return {"bucket_ts": ts, "o": o, "h": h, "l": l, "c": c}


def _fd(bucket_ts, price, side, vol):
    return {"type": "footprint_delta", "bucket_ts": bucket_ts, "price": price, "side": side, "delta_vol": vol}


def test_build_ohlc_bars_bucket_boundaries_and_high_low():
    ticks = [
        _tick(0.0, 100.0), _tick(30.0, 105.0), _tick(59.9, 98.0),
        _tick(60.0, 110.0), _tick(90.0, 108.0),
    ]
    bars = build_ohlc_bars(ticks, bucket_sec=60.0)
    assert [b["bucket_ts"] for b in bars] == [0.0, 60.0]
    assert bars[0] == {"bucket_ts": 0.0, "o": 100.0, "h": 105.0, "l": 98.0, "c": 98.0}
    assert bars[1] == {"bucket_ts": 60.0, "o": 110.0, "h": 110.0, "l": 108.0, "c": 108.0}


def test_build_ohlc_bars_sorts_unsorted_input():
    ticks = [_tick(60.0, 110.0), _tick(0.0, 100.0)]
    bars = build_ohlc_bars(ticks, bucket_sec=60.0)
    assert [b["bucket_ts"] for b in bars] == [0.0, 60.0]


def test_resample_bars_groups_by_factor_with_ohlc():
    bars = [_bar(float(i * 60), 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(3)]
    out = resample_bars(bars, factor=3)
    assert len(out) == 1
    assert out[0]["bucket_ts"] == 0.0
    assert out[0]["o"] == 100.0
    assert out[0]["h"] == 103.0  # max(h) of bars 0,1,2 = 101,102,103
    assert out[0]["l"] == 99.0   # min(l) of bars 0,1,2 = 99,100,101
    assert out[0]["c"] == 102.5  # 마지막 바(idx2)의 c = 100.5+2


def test_resample_bars_drops_incomplete_trailing_group():
    bars = [_bar(float(i * 60), 100.0, 101.0, 99.0, 100.0) for i in range(5)]
    out = resample_bars(bars, factor=3)
    assert len(out) == 1  # 5바 중 마지막 2개(미완성 그룹)는 버림


def test_build_trend_filter_holds_before_first_event_then_forward_fills_direction():
    # k=1로 swing 창을 좁혀 5바만으로 BOS 하나를 만든다.
    # swings(h,l,k=1): swing high idx=1(h=8), swing low idx=2(l=5).
    # market_structure: idx3에서 c=9.5가 직전 swing high(8) 상향 돌파 -> BOS bullish.
    bars = [
        _bar(0.0, 5.0, 5.0, 4.0, 4.5),
        _bar(60.0, 8.0, 8.0, 7.0, 7.5),
        _bar(120.0, 6.0, 6.0, 5.0, 5.5),
        _bar(180.0, 10.0, 10.0, 9.0, 9.5),
        _bar(240.0, 10.0, 10.0, 9.0, 9.5),
    ]
    out = build_trend_filter(bars, k=1)
    assert out == ["HOLD", "HOLD", "HOLD", "BUY", "BUY"]


def test_build_key_level_filter_proximity_in_and_out_of_range():
    # h 전부 20(동률) -> swing high 없음(count!=1 걸림). l=[10,10,5,10,10] -> idx2에서
    # swing low(=5) 유일 확정. levels=[(5.0,"BUY")]. c는 5.003(0.06%,in)/100.0(멀음)/
    # 5.0(정확히 일치,in)/5.006(0.12%,out)/200.0(멀음) — proximity_pct=0.001(0.1%) 기준.
    bars = [
        _bar(0.0, 20.0, 20.0, 10.0, 5.003),
        _bar(60.0, 20.0, 20.0, 10.0, 100.0),
        _bar(120.0, 20.0, 20.0, 5.0, 5.0),
        _bar(180.0, 20.0, 20.0, 10.0, 5.006),
        _bar(240.0, 20.0, 20.0, 10.0, 200.0),
    ]
    out = build_key_level_filter(bars, proximity_pct=0.001)
    assert out == ["BUY", "HOLD", "BUY", "HOLD", "HOLD"]
