from orderflow.models import TradeEvent
from research.ict.paper.reversal_triggers import (
    LTFBarBuilder,
    check_absorption,
    check_divergence,
    check_stop_run,
)


def test_check_absorption_detects_sell_dominance_without_price_drop_as_buy_signal():
    bar = {"open": 100.0, "close": 100.2}
    result = check_absorption(bar, buy_vol=3.0, sell_vol=27.0, rolling_median=1.0)
    assert result == "buy"


def test_check_absorption_returns_none_below_noise_floor():
    bar = {"open": 100.0, "close": 100.2}
    result = check_absorption(bar, buy_vol=3.0, sell_vol=4.0, rolling_median=5.0)
    assert result is None


def test_check_absorption_returns_none_before_warmup():
    bar = {"open": 100.0, "close": 100.2}
    result = check_absorption(bar, buy_vol=3.0, sell_vol=27.0, rolling_median=0.0)
    assert result is None


def test_check_stop_run_detects_bullish_stop_run():
    recent_bars = [{"open": 100 + i, "high": 105, "low": 95, "close": 100} for i in range(20)]
    bar = {"open": 100, "high": 101, "low": 90, "close": 96}
    result = check_stop_run(bar, recent_bars, total_vol=100.0, rolling_median=1.0)
    assert result == "buy"


def test_check_stop_run_returns_none_when_lookback_insufficient():
    bar = {"open": 100, "high": 101, "low": 90, "close": 96}
    result = check_stop_run(bar, recent_bars=[], total_vol=100.0, rolling_median=1.0)
    assert result is None


def test_check_divergence_detects_bearish_divergence_on_new_high_with_sell_delta():
    recent_bars = [{"high": 100, "low": 90} for _ in range(20)]
    bar = {"high": 105, "low": 96}
    result = check_divergence(bar, recent_bars, net_delta=-50.0, total_vol=100.0)
    assert result == "sell"


def test_check_divergence_returns_none_when_delta_ratio_too_small():
    recent_bars = [{"high": 100, "low": 90} for _ in range(20)]
    bar = {"high": 105, "low": 96}
    result = check_divergence(bar, recent_bars, net_delta=-5.0, total_vol=100.0)
    assert result is None


def test_ltf_bar_builder_finalizes_bar_with_absorption_trigger_on_bucket_rollover():
    builder = LTFBarBuilder(bucket_sec=60.0)
    # 워밍업(버킷0): 작은 체결로 rolling median을 낮게 유지
    for i in range(20):
        builder.on_trade(TradeEvent(symbol="BTC.HL", ts=float(i), price=99.0, size=0.1, side="buy"))

    # 버킷1: 매도 우세(27) vs 매수(3), 종가>=시가 → 흡수(강세) 신호가 나야 함
    bucket1_trades = [
        TradeEvent(symbol="BTC.HL", ts=60.0, price=100.0, size=3.0, side="buy"),
        TradeEvent(symbol="BTC.HL", ts=70.0, price=100.1, size=9.0, side="sell"),
        TradeEvent(symbol="BTC.HL", ts=80.0, price=100.2, size=9.0, side="sell"),
        TradeEvent(symbol="BTC.HL", ts=90.0, price=100.2, size=9.0, side="sell"),
    ]
    for t in bucket1_trades:
        builder.on_trade(t)

    # 버킷2 진입 트레이드 — 이 시점에 버킷1이 finalize된다
    result = builder.on_trade(TradeEvent(symbol="BTC.HL", ts=121.0, price=100.5, size=1.0, side="buy"))

    assert result is not None
    assert result["bar"]["open"] == 100.0
    assert result["bar"]["high"] == 100.2
    assert result["bar"]["low"] == 100.0
    assert result["bar"]["close"] == 100.2
    assert result["of_trigger"] == "absorption"
    assert result["side"] == "buy"
    assert len(builder.bars) == 2  # 버킷0, 버킷1 둘 다 완성됨
