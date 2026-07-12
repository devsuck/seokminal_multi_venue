from unittest.mock import patch

from orderflow.aggregator import OrderflowAggregator
from orderflow.models import TradeEvent
from research.hypotheses.orderflow_context_gate import (
    build_gated_confluence_signals,
    build_key_level_filter,
    build_ohlc_bars,
    build_trend_filter,
    build_vwap_filter,
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


def test_build_vwap_filter_close_above_vwap_is_buy():
    # bucket0: price=100,vol=10. bucket1: price=110,vol=10.
    # idx0: window=[100](자기자신만) -> VWAP=100, close=100 -> HOLD(같음).
    # idx1: window=[100,110],vol=[10,10] -> VWAP=105, close=110>105 -> BUY.
    deltas = [
        _fd(0.0, 100.0, "buy", 10.0),
        _fd(60.0, 110.0, "buy", 10.0),
    ]
    out = build_vwap_filter(deltas, window_buckets=10)
    assert out == ["HOLD", "BUY"]


def test_build_vwap_filter_close_below_vwap_is_sell():
    # bucket2 추가: price=90,vol=10. idx2 window=[100,110,90]vol=[10,10,10] ->
    # VWAP=(100+110+90)/3=100, close=90<100 -> SELL.
    deltas = [
        _fd(0.0, 100.0, "buy", 10.0),
        _fd(60.0, 110.0, "buy", 10.0),
        _fd(120.0, 90.0, "sell", 10.0),
    ]
    out = build_vwap_filter(deltas, window_buckets=10)
    assert out[2] == "SELL"


def test_build_vwap_filter_window_excludes_older_buckets():
    # bucket0: price=50,vol=100(거대 볼륨) bucket1: price=200,vol=1 bucket2: price=150,vol=1.
    # 전체창(10): VWAP=(50*100+200+150)/102≈52.45 -> close=150 > VWAP -> BUY.
    # 좁은창(2): idx2 기준 [bucket1,bucket2]만 -> VWAP=(200+150)/2=175 -> close=150 < VWAP -> SELL.
    deltas = [
        _fd(0.0, 50.0, "buy", 100.0),
        _fd(60.0, 200.0, "buy", 1.0),
        _fd(120.0, 150.0, "buy", 1.0),
    ]
    full = build_vwap_filter(deltas, window_buckets=10)
    windowed = build_vwap_filter(deltas, window_buckets=2)
    assert full[2] == "BUY"
    assert windowed[2] == "SELL"


# build_gated_confluence_signals는 build_trend_filter/build_key_level_filter/
# build_vwap_filter/build_ohlc_bars/resample_bars/build_confluence_signals를 조립만
# 하는 함수라, 각 구성요소는 이미 위에서 단위테스트했다. 여기서는 조립 로직(3필터
# 만장일치 bias, 15분봉->60s 브로드캐스트, killzone 게이팅, confluence 일치 확인)만
# 독립적으로 검증하기 위해 구성요소를 mock으로 고정한다.

_KZ_OUTSIDE = 1704115740.0  # 2024-01-01 13:29:00 UTC — 킬존(13:30-15:00) 밖
_KZ_START = 1704115800.0    # 2024-01-01 13:30:00 UTC — 킬존 시작(포함)
_KZ_INSIDE = 1704115860.0   # 2024-01-01 13:31:00 UTC — 킬존 안


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_all_agree_in_killzone_yields_signal(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_OUTSIDE, 100.0, "buy", 1.0),
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    # 룩어헤드 수정 이후: 봉이 하나뿐이면 "마감됐다"고 증명할 다음 봉이 없어 그 봉 신호를
    # 절대 쓸 수 없다(항상 HOLD). idx1(_KZ_START)부터 bar0가 마감됐음을 보여주기 위해
    # bar1(dummy)을 _KZ_START 시각에 시작하는 걸로 추가한다 -> idx1,idx2는 "직전에 마감된
    # bar0"의 신호(BUY)를 참조하게 된다.
    mock_resample.return_value = [{"bucket_ts": _KZ_OUTSIDE}, {"bucket_ts": _KZ_START}]
    mock_trend.return_value = ["BUY", "BUY"]
    mock_key_level.return_value = ["BUY", "BUY"]
    mock_vwap.return_value = ["BUY", "BUY", "BUY"]
    mock_confluence.return_value = {
        "closes": [100.0, 101.0, 102.0], "signals": ["BUY", "BUY", "BUY"], "eligible": [0, 1, 2],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["closes"] == [100.0, 101.0, 102.0]
    assert result["eligible"] == [0, 1, 2]
    # idx0: bar0가 아직 마감 전(형성 중)이라 bias 자체가 성립 불가 -> HOLD(킬존 밖이기도 함).
    # idx1,idx2: 마감된 bar0의 신호로 만장일치 + 킬존 안 + confluence 일치 -> BUY.
    assert result["signals"] == ["HOLD", "BUY", "BUY"]


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_filter_disagreement_is_hold(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_OUTSIDE, 100.0, "buy", 1.0),
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_OUTSIDE}]
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["SELL"]  # 트렌드와 불일치 -> bias 성립 안 함
    mock_vwap.return_value = ["BUY", "BUY", "BUY"]
    mock_confluence.return_value = {
        "closes": [100.0, 101.0, 102.0], "signals": ["BUY", "BUY", "BUY"], "eligible": [0, 1, 2],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["signals"] == ["HOLD", "HOLD", "HOLD"]


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_confluence_mismatch_is_hold(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_START}]
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["BUY"]
    mock_vwap.return_value = ["BUY", "BUY"]
    # bias는 BUY 성립(만장일치)이지만 confluence가 SELL -> 진입 신호는 HOLD.
    mock_confluence.return_value = {
        "closes": [101.0, 102.0], "signals": ["SELL", "SELL"], "eligible": [0, 1],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["signals"] == ["HOLD", "HOLD"]


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_before_warmup_is_not_eligible(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_OUTSIDE, 100.0, "buy", 1.0),  # 15분봉 워밍업 전(첫 15분봉보다 이름)
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_START}]  # 워밍업 완료선 = idx1과 동일 시각
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["BUY"]
    mock_vwap.return_value = ["BUY", "BUY", "BUY"]
    mock_confluence.return_value = {
        "closes": [100.0, 101.0, 102.0], "signals": ["BUY", "BUY", "BUY"], "eligible": [1, 2],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["eligible"] == [1, 2]  # idx0은 워밍업 전 -> 판정 불가 모집단에서 제외
    assert result["signals"][0] == "HOLD"


def test_build_gated_confluence_signals_no_lookahead_in_first_forming_bar_window():
    """룩어헤드 회귀 가드 — 위 4개 테스트와 달리 아무것도 mock하지 않고 실제 틱 데이터를
    build_ohlc_bars/resample_bars/build_trend_filter/build_key_level_filter/
    build_vwap_filter/build_confluence_signals 전체 실파이프라인으로 통과시킨다.

    45분(첫 15분봉 3개 완결 구간)짜리 실틱을 만들어 build_gated_confluence_signals를
    직접 호출한다. 첫 15분봉(bucket_ts=0~840, 아직 마감 안 됨)의 구간에 속하는 모든 60s
    버킷은 그 어떤 15분봉 신호도 참조할 수 없어야 하므로(마감된 봉이 하나도 없음)
    signals가 전부 "HOLD"여야 한다 — 이게 깨지면 _broadcast_15m_to_60s가 형성 중인
    봉 자신(또는 그보다 미래)의 신호를 과거 버킷에 흘려보내는 룩어헤드 버그가 재발한 것."""
    ticks = []
    for minute in range(45):
        base = float(minute * 60)
        price = 100.0 + minute * 0.5
        ticks.append({"ts": base + 10.0, "price": price, "size": 1.0, "side": "buy"})
        ticks.append({"ts": base + 40.0, "price": price + 0.1, "size": 1.0, "side": "sell"})

    agg = OrderflowAggregator()
    deltas = []
    for t in sorted(ticks, key=lambda x: x["ts"]):
        ev = TradeEvent(symbol="BTC.HL", ts=t["ts"], price=t["price"], size=t["size"], side=t["side"])
        deltas.append(agg.on_trade(ev))

    result = build_gated_confluence_signals(deltas, ticks)

    assert len(result["signals"]) == 45  # 45개 60s 버킷(45분치) 전부 판정 대상
    # 첫 15분봉 구간(60s 버킷 idx0~14, bucket_ts 0~840)은 마감된 15분봉이 하나도 없으므로
    # bias가 절대 성립할 수 없다 -> 전부 HOLD.
    assert result["signals"][:15] == ["HOLD"] * 15
