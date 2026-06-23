import pytest

from condition_engine.parser import ConditionSet
from strategy_spawner.spawner_parser import SpawnerParser, SpawnRule

BAR_TYPE = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


def _condition_dict():
    return {
        "combinator": "AND",
        "conditions": [
            {
                "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                "op": "<",
                "right": {"value": 30},
            }
        ],
    }


def test_parse_single_valid_rule():
    rules = SpawnerParser.parse(
        [
            {
                "condition": _condition_dict(),
                "strategy": {
                    "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                    "params": {"trade_size": 100},
                },
            }
        ]
    )

    assert len(rules) == 1
    rule = rules[0]
    assert isinstance(rule, SpawnRule)
    assert isinstance(rule.condition_set, ConditionSet)
    from tests.fixtures.dummy_strategy import DummyStrategy

    assert rule.strategy_class is DummyStrategy
    assert rule.params == {"trade_size": 100}


def test_parse_multiple_rules():
    rules = SpawnerParser.parse(
        [
            {
                "condition": _condition_dict(),
                "strategy": {
                    "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                    "params": {"trade_size": 100},
                },
            },
            {
                "condition": _condition_dict(),
                "strategy": {
                    "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                    "params": {"trade_size": 200},
                },
            },
        ]
    )

    assert len(rules) == 2
    assert rules[0].params == {"trade_size": 100}
    assert rules[1].params == {"trade_size": 200}


def test_parse_delegates_condition_errors_to_condition_parser():
    with pytest.raises(ValueError, match="combinator"):
        SpawnerParser.parse(
            [
                {
                    "condition": {"combinator": "XOR", "conditions": []},
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                        "params": {},
                    },
                }
            ]
        )


def test_parse_rejects_malformed_class_string():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {"class": "no-colon-here", "params": {}},
                }
            ]
        )


def test_parse_rejects_unimportable_module():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {"class": "nonexistent.module:Foo", "params": {}},
                }
            ]
        )


def test_parse_rejects_missing_class_in_module():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:NoSuchClass",
                        "params": {},
                    },
                }
            ]
        )


def test_parse_rejects_non_strategy_class():
    with pytest.raises(ValueError, match="Strategy"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:NotAStrategy",
                        "params": {},
                    },
                }
            ]
        )


def test_parse_raises_value_error_missing_condition_key():
    with pytest.raises(ValueError, match="condition"):
        SpawnerParser.parse(
            [
                {
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                        "params": {},
                    },
                }
            ]
        )


def test_parse_raises_value_error_missing_strategy_key():
    with pytest.raises(ValueError, match="strategy"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                }
            ]
        )


def test_parse_raises_value_error_missing_class_key():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {
                        "params": {},
                    },
                }
            ]
        )
