from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from backtest_runner.gated_strategy import make_gated_strategy_class
from condition_engine.parser import ConditionParser

BAR_TYPE = "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL"


class DummyInnerStrategy(Strategy):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs
        self.bars_seen: list = []

    def on_bar(self, bar) -> None:
        self.bars_seen.append(bar)


def _bar(price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(BAR_TYPE),
        open=Price.from_str(f"{price}.00"),
        high=Price.from_str(f"{price + 1}.00"),
        low=Price.from_str(f"{price - 1}.00"),
        close=Price.from_str(f"{price}.00"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def _ma_above_80_condition():
    return ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE,
                        "params": {"period": 2, "ma_type": "SIMPLE"},
                    },
                    "op": ">",
                    "right": {"value": 80},
                }
            ],
        }
    )


def test_gated_strategy_suppresses_on_bar_before_condition_true():
    gated_cls = make_gated_strategy_class(DummyInnerStrategy, _ma_above_80_condition())
    strategy = gated_cls()

    strategy.on_bar(_bar(50, 0))
    strategy.on_bar(_bar(50, 1))

    assert strategy.bars_seen == []


def test_gated_strategy_forwards_on_bar_from_trigger_bar_onward():
    gated_cls = make_gated_strategy_class(DummyInnerStrategy, _ma_above_80_condition())
    strategy = gated_cls()

    bar0 = _bar(50, 0)
    bar1 = _bar(50, 1)
    bar2 = _bar(100, 2)  # MA(2) of [50, 100] = 75, still <= 80
    bar3 = _bar(100, 3)  # MA(2) of [100, 100] = 100, > 80 -> trigger here
    bar4 = _bar(100, 4)

    for bar in [bar0, bar1, bar2, bar3, bar4]:
        strategy.on_bar(bar)

    assert strategy.bars_seen == [bar3, bar4]
