from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from condition_engine.parser import ConditionParser
from strategy_spawner.spawner import StrategySpawner
from strategy_spawner.spawner_parser import SpawnRule
from tests.fixtures.dummy_strategy import DummyStrategy

BAR_TYPE_AAPL = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"
BAR_TYPE_MSFT = "MSFT.NASDAQ-1-MINUTE-LAST-EXTERNAL"


class RecordingEngine:
    def __init__(self) -> None:
        self.added: list = []

    def add_strategy(self, strategy) -> None:
        self.added.append(strategy)


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


def _obv_rule(op: str, threshold: float, params: dict) -> SpawnRule:
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": op,
                    "right": {"value": threshold},
                }
            ],
        }
    )
    return SpawnRule(condition_set=condition_set, strategy_class=DummyStrategy, params=params)


def test_no_spawn_before_condition_true():
    rule = _obv_rule(">=", 0, {"trade_size": 1})
    engine = RecordingEngine()
    spawner = StrategySpawner([rule], engine)

    assert engine.added == []
    assert spawner.spawned_count == 0


def test_spawns_exactly_once_with_rule_params():
    rule = _obv_rule(">=", 0, {"trade_size": 42})
    engine = RecordingEngine()
    spawner = StrategySpawner([rule], engine)

    spawner.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert len(engine.added) == 1
    assert isinstance(engine.added[0], DummyStrategy)
    assert engine.added[0].kwargs == {"trade_size": 42}
    assert spawner.spawned_count == 1


def test_does_not_respawn_after_first_trigger():
    rule = _obv_rule(">=", 0, {"trade_size": 1})
    engine = RecordingEngine()
    spawner = StrategySpawner([rule], engine)

    spawner.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))
    spawner.on_bar(_bar(BAR_TYPE_AAPL, 101.0, 1))
    spawner.on_bar(_bar(BAR_TYPE_AAPL, 102.0, 2))

    assert len(engine.added) == 1
    assert spawner.spawned_count == 1


def test_only_triggered_rule_spawns_among_multiple():
    never_true_rule = _obv_rule("<", -1000, {"trade_size": 1})
    always_true_rule = _obv_rule(">=", 0, {"trade_size": 2})
    engine = RecordingEngine()
    spawner = StrategySpawner([never_true_rule, always_true_rule], engine)

    spawner.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert len(engine.added) == 1
    assert engine.added[0].kwargs == {"trade_size": 2}
    assert spawner.spawned_count == 1
