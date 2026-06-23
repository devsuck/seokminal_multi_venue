from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from condition_engine.parser import ConditionParser
from strategy_spawner.spawner import StrategySpawner
from strategy_spawner.spawner_parser import SpawnRule
from tests.fixtures.dummy_strategy import DummyStrategy

BAR_TYPE_AAPL = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


def _bar(price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(BAR_TYPE_AAPL),
        open=Price.from_str(f"{price}"),
        high=Price.from_str(f"{price}"),
        low=Price.from_str(f"{price}"),
        close=Price.from_str(f"{price}"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_spawned_strategy_is_registered_on_real_backtest_engine():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                }
            ],
        }
    )
    rule = SpawnRule(condition_set=condition_set, strategy_class=DummyStrategy, params={})
    engine = BacktestEngine()
    spawner = StrategySpawner([rule], engine)

    spawner.on_bar(_bar(100.0, 0))

    assert spawner.spawned_count == 1
    states = engine.trader.strategy_states()
    assert len(states) == 1
    assert list(states.values())[0] == "READY"
