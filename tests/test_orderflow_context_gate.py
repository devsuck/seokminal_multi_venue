from research.hypotheses.orderflow_context_gate import (
    build_ohlc_bars,
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
