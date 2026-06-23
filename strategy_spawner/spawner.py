from nautilus_trader.model.data import Bar

from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry
from strategy_spawner.spawner_parser import SpawnRule


class StrategySpawner:
    def __init__(self, rules: list[SpawnRule], engine) -> None:
        self._engine = engine
        self._entries = [
            {
                "rule": rule,
                "evaluator": ConditionEvaluator(rule.condition_set, IndicatorRegistry()),
                "spawned": False,
            }
            for rule in rules
        ]

    def on_bar(self, bar: Bar) -> None:
        for entry in self._entries:
            entry["evaluator"].on_bar(bar)

        for entry in self._entries:
            if entry["spawned"]:
                continue
            if entry["evaluator"].evaluate():
                rule = entry["rule"]
                strategy = rule.strategy_class(**rule.params)
                self._engine.add_strategy(strategy)
                entry["spawned"] = True

    @property
    def spawned_count(self) -> int:
        return sum(1 for entry in self._entries if entry["spawned"])
