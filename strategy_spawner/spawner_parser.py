import importlib
from dataclasses import dataclass

from nautilus_trader.trading.strategy import Strategy

from condition_engine.parser import ConditionParser, ConditionSet


@dataclass(frozen=True)
class SpawnRule:
    condition_set: ConditionSet
    strategy_class: type
    params: dict


class SpawnerParser:
    @staticmethod
    def parse(json_list: list[dict]) -> list[SpawnRule]:
        return [SpawnerParser._parse_rule(entry) for entry in json_list]

    @staticmethod
    def _parse_rule(entry: dict) -> SpawnRule:
        try:
            condition_dict = entry["condition"]
        except KeyError as exc:
            raise ValueError("missing required key 'condition' in spawn rule") from exc

        try:
            strategy_dict = entry["strategy"]
        except KeyError as exc:
            raise ValueError("missing required key 'strategy' in spawn rule") from exc

        condition_set = ConditionParser.parse(condition_dict)

        try:
            class_path = strategy_dict["class"]
        except KeyError as exc:
            raise ValueError(
                "missing required key 'class' in strategy dict"
            ) from exc

        strategy_class = SpawnerParser._resolve_strategy_class(class_path)
        params = strategy_dict.get("params", {})
        return SpawnRule(
            condition_set=condition_set,
            strategy_class=strategy_class,
            params=params,
        )

    @staticmethod
    def _resolve_strategy_class(class_path: str) -> type:
        if ":" not in class_path:
            raise ValueError(
                f"invalid strategy class path (expected 'module:Class'): {class_path!r}"
            )
        module_path, _, class_name = class_path.rpartition(":")

        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            raise ValueError(f"invalid strategy class path: {class_path!r}") from exc

        try:
            cls = getattr(module, class_name)
        except AttributeError as exc:
            raise ValueError(f"invalid strategy class path: {class_path!r}") from exc

        if not isinstance(cls, type) or not issubclass(cls, Strategy):
            raise ValueError(
                f"{class_path!r} does not resolve to a Strategy subclass"
            )

        return cls
