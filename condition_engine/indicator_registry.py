from nautilus_trader.indicators.averages import MovingAverageFactory, MovingAverageType
from nautilus_trader.indicators.momentum import (
    CommodityChannelIndex,
    RelativeStrengthIndex,
)
from nautilus_trader.indicators.trend import MovingAverageConvergenceDivergence
from nautilus_trader.indicators.volatility import BollingerBands
from nautilus_trader.indicators.volume import OnBalanceVolume
from nautilus_trader.model.data import Bar

from condition_engine.parser import IndicatorOperand


def _build_rsi(params: dict):
    ma_type = MovingAverageType[params.get("ma_type", "SIMPLE")]
    return RelativeStrengthIndex(period=params["period"], ma_type=ma_type)


def _build_ma(params: dict):
    ma_type = MovingAverageType[params["ma_type"]]
    return MovingAverageFactory.create(params["period"], ma_type)


def _build_bb(params: dict):
    ma_type = MovingAverageType[params.get("ma_type", "SIMPLE")]
    return BollingerBands(period=params["period"], k=params["k"], ma_type=ma_type)


def _build_macd(params: dict):
    ma_type = MovingAverageType[params.get("ma_type", "EXPONENTIAL")]
    return MovingAverageConvergenceDivergence(
        fast_period=params["fast_period"],
        slow_period=params["slow_period"],
        ma_type=ma_type,
    )


def _build_cci(params: dict):
    ma_type = MovingAverageType[params.get("ma_type", "SIMPLE")]
    return CommodityChannelIndex(
        period=params["period"],
        scalar=params.get("scalar", 0.015),
        ma_type=ma_type,
    )


def _build_obv(params: dict):
    return OnBalanceVolume(period=params.get("period", 0))


_BUILDERS = {
    "RSI": _build_rsi,
    "MA": _build_ma,
    "BB": _build_bb,
    "MACD": _build_macd,
    "CCI": _build_cci,
    "OBV": _build_obv,
}


class IndicatorRegistry:
    def __init__(self) -> None:
        self._indicators: dict[tuple, object] = {}
        self._bars_by_type: dict[str, list[Bar]] = {}

    def get_or_create(self, operand: IndicatorOperand):
        key = self._key(operand)
        if key not in self._indicators:
            indicator = _BUILDERS[operand.indicator](operand.params)
            self._indicators[key] = indicator
            # Feed all buffered bars of this type to the new indicator
            bar_type_str = operand.bar_type
            if bar_type_str in self._bars_by_type:
                for bar in self._bars_by_type[bar_type_str]:
                    indicator.handle_bar(bar)
        return self._indicators[key]

    def on_bar(self, bar: Bar) -> None:
        bar_type_str = str(bar.bar_type)
        # Buffer this bar for later indicators
        if bar_type_str not in self._bars_by_type:
            self._bars_by_type[bar_type_str] = []
        self._bars_by_type[bar_type_str].append(bar)
        # Update all existing indicators that match this bar type
        for (key_bar_type, _indicator, _params), indicator in self._indicators.items():
            if key_bar_type == bar_type_str:
                indicator.handle_bar(bar)

    def current_value(self, operand: IndicatorOperand) -> float | None:
        indicator = self.get_or_create(operand)
        if not indicator.initialized:
            return None
        if operand.indicator == "BB":
            return getattr(indicator, operand.params["band"])
        return indicator.value

    @staticmethod
    def _key(operand: IndicatorOperand) -> tuple:
        return (operand.bar_type, operand.indicator, tuple(sorted(operand.params.items())))
