import pytest

from condition_engine.parser import (
    Comparison,
    ConditionParser,
    ConditionSet,
    IndicatorOperand,
    LiteralOperand,
)

BAR_TYPE = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


def test_parse_literal_comparison():
    result = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                    "op": "<",
                    "right": {"value": 30},
                }
            ],
        }
    )

    assert result == ConditionSet(
        combinator="AND",
        comparisons=[
            Comparison(
                left=IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE, params={"period": 14}),
                op="<",
                right=LiteralOperand(value=30),
            )
        ],
    )


def test_parse_indicator_vs_indicator_comparison():
    result = ConditionParser.parse(
        {
            "combinator": "OR",
            "conditions": [
                {
                    "left": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE,
                        "params": {"period": 20, "ma_type": "SIMPLE"},
                    },
                    "op": ">",
                    "right": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE,
                        "params": {"period": 50, "ma_type": "SIMPLE"},
                    },
                }
            ],
        }
    )

    assert result.combinator == "OR"
    assert len(result.comparisons) == 1
    assert result.comparisons[0].op == ">"


def test_parse_multiple_conditions_in_one_set():
    result = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                    "op": "<",
                    "right": {"value": 30},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
            ],
        }
    )

    assert len(result.comparisons) == 2


def test_parse_rejects_unknown_combinator():
    with pytest.raises(ValueError, match="combinator"):
        ConditionParser.parse(
            {
                "combinator": "XOR",
                "conditions": [],
            }
        )


def test_parse_rejects_unknown_indicator():
    with pytest.raises(ValueError, match="indicator"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "FOO", "bar_type": BAR_TYPE, "params": {}},
                        "op": "<",
                        "right": {"value": 1},
                    }
                ],
            }
        )


def test_parse_rejects_unsupported_op():
    with pytest.raises(ValueError, match="op"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                        "op": "!=",
                        "right": {"value": 30},
                    }
                ],
            }
        )


def test_parse_rejects_missing_required_param():
    with pytest.raises(ValueError, match="period"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {}},
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        )


def test_parse_rejects_invalid_bar_type():
    with pytest.raises(ValueError, match="bar_type"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {
                            "indicator": "RSI",
                            "bar_type": "not-a-real-bar-type",
                            "params": {"period": 14},
                        },
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        )
