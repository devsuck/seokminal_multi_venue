from nautilus_trader.model.data import Bar

from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import ConditionSet


def make_gated_strategy_class(strategy_class: type, condition_set: ConditionSet) -> type:
    class _Gated(strategy_class):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
            self._armed = False

        def on_bar(self, bar: Bar) -> None:
            self._evaluator.on_bar(bar)
            if not self._armed:
                if not self._evaluator.evaluate():
                    return
                self._armed = True
            super().on_bar(bar)

    return _Gated
