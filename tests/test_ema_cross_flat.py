from decimal import Decimal

from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from backtest_runner.ema_cross_flat import EMACrossFlat


def test_ema_cross_flat_converts_flat_kwargs_to_config():
    strategy = EMACrossFlat(
        instrument_id="AAPL.NASDAQ",
        bar_type="AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
        trade_size=10,
        fast_ema_period=3,
        slow_ema_period=5,
    )

    assert strategy.config.instrument_id == InstrumentId.from_str("AAPL.NASDAQ")
    assert strategy.config.bar_type == BarType.from_str("AAPL.NASDAQ-1-DAY-LAST-EXTERNAL")
    assert strategy.config.trade_size == Decimal("10")
    assert strategy.config.fast_ema_period == 3
    assert strategy.config.slow_ema_period == 5
    assert strategy.config.request_bars is False
    assert strategy.config.subscribe_trade_ticks is False


def test_ema_cross_flat_uses_default_periods_when_omitted():
    strategy = EMACrossFlat(
        instrument_id="AAPL.NASDAQ",
        bar_type="AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
        trade_size=10,
    )

    assert strategy.config.fast_ema_period == 10
    assert strategy.config.slow_ema_period == 20
