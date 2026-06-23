from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import IndicatorOperand

BAR_TYPE_AAPL = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"
BAR_TYPE_MSFT = "MSFT.NASDAQ-1-MINUTE-LAST-EXTERNAL"


def _bar(bar_type_str: str, price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(bar_type_str),
        open=Price.from_str(f"{price}"),
        high=Price.from_str(f"{price}"),
        low=Price.from_str(f"{price}"),
        close=Price.from_str(f"{price}"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_rsi_not_initialized_before_enough_bars():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_AAPL, params={"period": 14})

    assert registry.current_value(operand) is None


def test_rsi_initializes_and_produces_value_after_enough_bars():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_AAPL, params={"period": 3})

    for i, price in enumerate([100.0, 101.0, 99.0, 102.0, 103.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    value = registry.current_value(operand)
    assert value is not None
    assert isinstance(value, float)


def test_on_bar_only_updates_matching_bar_type():
    registry = IndicatorRegistry()
    aapl_operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_AAPL, params={"period": 2})
    msft_operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_MSFT, params={"period": 2})

    for i, price in enumerate([100.0, 101.0, 99.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    assert registry.current_value(aapl_operand) is not None
    assert registry.current_value(msft_operand) is None


def test_ma_uses_required_ma_type_param():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(
        indicator="MA", bar_type=BAR_TYPE_AAPL, params={"period": 2, "ma_type": "SIMPLE"}
    )

    for i, price in enumerate([100.0, 102.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    assert registry.current_value(operand) == 101.0


def test_bollinger_bands_reads_selected_band():
    registry = IndicatorRegistry()
    upper_operand = IndicatorOperand(
        indicator="BB", bar_type=BAR_TYPE_AAPL, params={"period": 2, "k": 2.0, "band": "upper"}
    )
    lower_operand = IndicatorOperand(
        indicator="BB", bar_type=BAR_TYPE_AAPL, params={"period": 2, "k": 2.0, "band": "lower"}
    )

    for i, price in enumerate([100.0, 102.0, 104.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    upper = registry.current_value(upper_operand)
    lower = registry.current_value(lower_operand)
    assert upper is not None and lower is not None
    assert upper > lower


def test_obv_has_no_required_params():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(indicator="OBV", bar_type=BAR_TYPE_AAPL, params={})

    registry.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert registry.current_value(operand) is not None
