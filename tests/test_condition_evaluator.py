from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import ConditionParser

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


def test_uninitialized_indicator_evaluates_as_false_not_error():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "RSI", "bar_type": BAR_TYPE_AAPL, "params": {"period": 14}},
                    "op": "<",
                    "right": {"value": 30},
                }
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())

    assert evaluator.evaluate() is False


def test_and_combinator_requires_all_true():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": "<",
                    "right": {"value": -1000},
                },
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
    evaluator.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert evaluator.evaluate() is False


def test_or_combinator_requires_any_true():
    condition_set = ConditionParser.parse(
        {
            "combinator": "OR",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": "<",
                    "right": {"value": -1000},
                },
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
    evaluator.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert evaluator.evaluate() is True


def test_indicator_vs_indicator_golden_cross():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE_AAPL,
                        "params": {"period": 1, "ma_type": "SIMPLE"},
                    },
                    "op": ">",
                    "right": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE_AAPL,
                        "params": {"period": 2, "ma_type": "SIMPLE"},
                    },
                }
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
    for i, price in enumerate([100.0, 110.0]):
        evaluator.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    assert evaluator.evaluate() is True


def test_multi_instrument_evaluates_using_last_known_value():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_MSFT, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())

    # Only AAPL ever receives a bar; MSFT's operand never initializes.
    evaluator.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    # MSFT leg is still uninitialized (None) -> overall False, not an error,
    # and evaluate() returns immediately without waiting for an MSFT bar.
    assert evaluator.evaluate() is False

    evaluator.on_bar(_bar(BAR_TYPE_MSFT, 50.0, 1))

    # Now both legs have at least one bar each -> AAPL's last known value is
    # still used even though no new AAPL bar arrived in between.
    assert evaluator.evaluate() is True
