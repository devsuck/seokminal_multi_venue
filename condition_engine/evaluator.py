import operator

from nautilus_trader.model.data import Bar

from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import Comparison, ConditionSet, LiteralOperand, Operand

_OPS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
}


class ConditionEvaluator:
    def __init__(self, condition_set: ConditionSet, registry: IndicatorRegistry) -> None:
        self._condition_set = condition_set
        self._registry = registry

    def on_bar(self, bar: Bar) -> None:
        self._registry.on_bar(bar)

    def evaluate(self) -> bool:
        results = [self._evaluate_comparison(c) for c in self._condition_set.comparisons]
        if self._condition_set.combinator == "AND":
            return all(results)
        return any(results)

    def _evaluate_comparison(self, comparison: Comparison) -> bool:
        left = self._resolve(comparison.left)
        right = self._resolve(comparison.right)
        if left is None or right is None:
            return False
        return _OPS[comparison.op](left, right)

    def _resolve(self, operand: Operand) -> float | None:
        if isinstance(operand, LiteralOperand):
            return operand.value
        return self._registry.current_value(operand)
