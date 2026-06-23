from dataclasses import dataclass, field
from typing import Union

from nautilus_trader.model.data import BarType

SUPPORTED_INDICATORS = {"RSI", "MA", "BB", "MACD", "CCI", "OBV"}
SUPPORTED_OPS = {"<", "<=", ">", ">=", "=="}
SUPPORTED_COMBINATORS = {"AND", "OR"}

REQUIRED_PARAMS: dict[str, set[str]] = {
    "RSI": {"period"},
    "MA": {"period", "ma_type"},
    "BB": {"period", "k", "band"},
    "MACD": {"fast_period", "slow_period"},
    "CCI": {"period"},
    "OBV": set(),
}


@dataclass(frozen=True)
class LiteralOperand:
    value: float


@dataclass(frozen=True)
class IndicatorOperand:
    indicator: str
    bar_type: str
    params: dict = field(default_factory=dict)


Operand = Union[LiteralOperand, IndicatorOperand]


@dataclass(frozen=True)
class Comparison:
    left: Operand
    op: str
    right: Operand


@dataclass(frozen=True)
class ConditionSet:
    combinator: str
    comparisons: list[Comparison]


class ConditionParser:
    @staticmethod
    def parse(json_dict: dict) -> ConditionSet:
        combinator = json_dict.get("combinator")
        if combinator not in SUPPORTED_COMBINATORS:
            raise ValueError(f"unknown combinator: {combinator!r}")

        comparisons = [
            ConditionParser._parse_comparison(c) for c in json_dict.get("conditions", [])
        ]
        return ConditionSet(combinator=combinator, comparisons=comparisons)

    @staticmethod
    def _parse_comparison(comparison_dict: dict) -> Comparison:
        left = ConditionParser._parse_operand(comparison_dict["left"])
        op = comparison_dict["op"]
        if op not in SUPPORTED_OPS:
            raise ValueError(f"unsupported op: {op!r}")
        right = ConditionParser._parse_operand(comparison_dict["right"])
        return Comparison(left=left, op=op, right=right)

    @staticmethod
    def _parse_operand(operand_dict: dict) -> Operand:
        if "value" in operand_dict:
            return LiteralOperand(value=operand_dict["value"])

        indicator = operand_dict.get("indicator")
        if indicator not in SUPPORTED_INDICATORS:
            raise ValueError(f"unknown indicator: {indicator!r}")

        bar_type = operand_dict["bar_type"]
        try:
            BarType.from_str(bar_type)
        except ValueError as exc:
            raise ValueError(f"invalid bar_type: {bar_type!r}") from exc

        params = operand_dict.get("params", {})
        missing = REQUIRED_PARAMS[indicator] - params.keys()
        if missing:
            raise ValueError(
                f"{indicator} missing required params: {sorted(missing)}"
            )

        return IndicatorOperand(indicator=indicator, bar_type=bar_type, params=params)
