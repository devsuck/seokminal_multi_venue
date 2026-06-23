# Condition Parser Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a JSON-configured, per-bar-incremental condition evaluator
(`condition_engine/`) that wraps Nautilus's existing RSI/MA/BB/MACD/CCI/OBV
indicators and answers true/false for multi-instrument, multi-timeframe
trading conditions.

**Architecture:** Three single-responsibility modules. `parser.py` turns a
JSON dict into a `ConditionSet` tree of dataclasses (validates eagerly,
raises `ValueError` on any bad input). `indicator_registry.py` lazily
constructs and updates real `nautilus_trader` indicator instances, keyed by
`(bar_type_str, indicator_name, sorted_params)` — a single `bar_type` string
(Nautilus's full `BarType` format) disambiguates instrument + timeframe, so
there's no separate `instrument_id` field to desync. `evaluator.py` glues
the two: `on_bar(bar)` forwards to the registry, `evaluate()` walks the
`ConditionSet` resolving each side (literal or current indicator value) and
combines with the flat `AND`/`OR` combinator. An uninitialized indicator
resolves to `None`, which makes that `Comparison` evaluate to `False` (not
an exception) — the normal state right after startup before indicators warm
up.

**Tech Stack:** `nautilus_trader` (already a dependency) — specifically
`nautilus_trader.model.data.{Bar, BarType}`,
`nautilus_trader.indicators.momentum.{RelativeStrengthIndex,
CommodityChannelIndex}`, `nautilus_trader.indicators.averages.{
MovingAverageFactory, MovingAverageType}`,
`nautilus_trader.indicators.volatility.BollingerBands`,
`nautilus_trader.indicators.trend.MovingAverageConvergenceDivergence`,
`nautilus_trader.indicators.volume.OnBalanceVolume`. `pytest` (already
configured). No broker library involved — no live verification step.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-23-condition-parser-engine-design.md`.
- Supported indicators (exactly these 6, by JSON `"indicator"` name):
  `RSI`, `MA`, `BB`, `MACD`, `CCI`, `OBV`.
- Supported comparison ops (exactly these 5): `<`, `<=`, `>`, `>=`, `==`.
- Combinator: flat `"AND"` or `"OR"` only — no nested trees.
- `bar_type` in JSON is always a full Nautilus `BarType` string (e.g.
  `"AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"`), parsed via `BarType.from_str`.
  There is no separate `instrument_id` field anywhere in this plan.
- Per-indicator required `params` (verified against installed
  `nautilus_trader` constructors — see spec for the doc-string evidence):
  - `RSI`: required `period`; optional `ma_type` (default `"SIMPLE"`).
  - `MA`: required `period`, `ma_type` (no default in
    `MovingAverageFactory.create`).
  - `BB`: required `period`, `k`, `band` (one of `"upper"`, `"middle"`,
    `"lower"` — `BollingerBands` has no single `.value`); optional `ma_type`
    (default `"SIMPLE"`).
  - `MACD`: required `fast_period`, `slow_period`; optional `ma_type`
    (default `"EXPONENTIAL"`).
  - `CCI`: required `period`; optional `scalar` (default `0.015`),
    `ma_type` (default `"SIMPLE"`).
  - `OBV`: no required params; optional `period` (default `0`).
- All validation (unknown indicator/op/combinator, missing required params,
  invalid `bar_type` string) happens in `ConditionParser.parse`, at parse
  time — never deferred to evaluation time.
- No Nautilus `Strategy`/`ExecutionEngine`/`TradingNode` integration, no
  nested condition trees, no dashboard/UI. All deferred per spec's "Out of
  scope" section.
- Verified directly against the installed `nautilus_trader` library in this
  environment (not assumed from docs):
  - All 6 indicator classes expose `.handle_bar(bar)`, `.initialized`
    (bool). `RelativeStrengthIndex`, `CommodityChannelIndex`,
    `OnBalanceVolume`, `MovingAverageConvergenceDivergence`, and
    `MovingAverage` (via `MovingAverageFactory.create`) expose `.value`.
    `BollingerBands` instead exposes `.upper`, `.middle`, `.lower` (no
    `.value`).
  - `MovingAverageType` is an enum-like class; members are looked up by
    name via `MovingAverageType["SIMPLE"]` (subscript, not attribute —
    confirmed this works against the installed version).
  - `Bar(bar_type, open, high, low, close, volume, ts_event, ts_init)`
    requires `Price.from_str(...)` for OHLC and `Quantity.from_str(...)` for
    volume (plain floats are rejected) — confirmed by constructing a real
    `Bar` against the installed library.
  - `BarType.from_str("AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL")` succeeds and
    `str(bar_type)` round-trips to the same string — this is the format
    used as the JSON `bar_type` value and as the `IndicatorRegistry` key.
  - `BarType.from_str` raises `ValueError` on a malformed string (used
    directly by the parser's validation).

---

### Task 1: `parser.py` — JSON to `ConditionSet`

**Files:**
- Create: `condition_engine/__init__.py` (empty)
- Create: `condition_engine/parser.py`
- Test: `tests/test_condition_parser.py`

**Interfaces:**
- Consumes: nothing from other tasks (this is the first task).
- Produces (consumed by Tasks 2 and 3):
  - `LiteralOperand(value: float)` — frozen dataclass.
  - `IndicatorOperand(indicator: str, bar_type: str, params: dict)` — frozen
    dataclass.
  - `Operand = LiteralOperand | IndicatorOperand`
  - `Comparison(left: Operand, op: str, right: Operand)` — frozen dataclass.
  - `ConditionSet(combinator: str, comparisons: list[Comparison])` — frozen
    dataclass (`combinator` is `"AND"` or `"OR"`).
  - `ConditionParser.parse(json_dict: dict) -> ConditionSet` (staticmethod).
  - `SUPPORTED_INDICATORS: set[str]`, `SUPPORTED_OPS: set[str]`,
    `REQUIRED_PARAMS: dict[str, set[str]]` (module-level constants Task 2
    does not need directly, but Task 2's builder dispatch table uses the
    same 6 indicator name strings).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_condition_parser.py
import pytest

from condition_engine.parser import (
    Comparison,
    ConditionParser,
    ConditionSet,
    IndicatorOperand,
    LiteralOperand,
)

BAR_TYPE = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


def test_parse_literal_comparison():
    result = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                    "op": "<",
                    "right": {"value": 30},
                }
            ],
        }
    )

    assert result == ConditionSet(
        combinator="AND",
        comparisons=[
            Comparison(
                left=IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE, params={"period": 14}),
                op="<",
                right=LiteralOperand(value=30),
            )
        ],
    )


def test_parse_indicator_vs_indicator_comparison():
    result = ConditionParser.parse(
        {
            "combinator": "OR",
            "conditions": [
                {
                    "left": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE,
                        "params": {"period": 20, "ma_type": "SIMPLE"},
                    },
                    "op": ">",
                    "right": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE,
                        "params": {"period": 50, "ma_type": "SIMPLE"},
                    },
                }
            ],
        }
    )

    assert result.combinator == "OR"
    assert len(result.comparisons) == 1
    assert result.comparisons[0].op == ">"


def test_parse_multiple_conditions_in_one_set():
    result = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                    "op": "<",
                    "right": {"value": 30},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
            ],
        }
    )

    assert len(result.comparisons) == 2


def test_parse_rejects_unknown_combinator():
    with pytest.raises(ValueError, match="combinator"):
        ConditionParser.parse(
            {
                "combinator": "XOR",
                "conditions": [],
            }
        )


def test_parse_rejects_unknown_indicator():
    with pytest.raises(ValueError, match="indicator"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "FOO", "bar_type": BAR_TYPE, "params": {}},
                        "op": "<",
                        "right": {"value": 1},
                    }
                ],
            }
        )


def test_parse_rejects_unsupported_op():
    with pytest.raises(ValueError, match="op"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                        "op": "!=",
                        "right": {"value": 30},
                    }
                ],
            }
        )


def test_parse_rejects_missing_required_param():
    with pytest.raises(ValueError, match="period"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {}},
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        )


def test_parse_rejects_invalid_bar_type():
    with pytest.raises(ValueError, match="bar_type"):
        ConditionParser.parse(
            {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {
                            "indicator": "RSI",
                            "bar_type": "not-a-real-bar-type",
                            "params": {"period": 14},
                        },
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_condition_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'condition_engine'`

- [ ] **Step 3: Implement `condition_engine/parser.py`**

```python
# condition_engine/parser.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_condition_parser.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add condition_engine/__init__.py condition_engine/parser.py tests/test_condition_parser.py
git commit -m "feat: add JSON condition parser for condition engine"
```

---

### Task 2: `indicator_registry.py` — Nautilus indicator lifecycle

**Files:**
- Create: `condition_engine/indicator_registry.py`
- Test: `tests/test_indicator_registry.py`

**Interfaces:**
- Consumes: `IndicatorOperand` (Task 1, exact fields `indicator`, `bar_type`,
  `params`).
- Produces (consumed by Task 3):
  - `IndicatorRegistry()` — no-arg constructor.
  - `IndicatorRegistry.get_or_create(operand: IndicatorOperand) -> indicator object`
  - `IndicatorRegistry.on_bar(bar: Bar) -> None`
  - `IndicatorRegistry.current_value(operand: IndicatorOperand) -> float | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_indicator_registry.py
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import IndicatorOperand

BAR_TYPE_AAPL = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"
BAR_TYPE_MSFT = "MSFT.NASDAQ-1-MINUTE-LAST-EXTERNAL"


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


def test_rsi_not_initialized_before_enough_bars():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_AAPL, params={"period": 14})

    assert registry.current_value(operand) is None


def test_rsi_initializes_and_produces_value_after_enough_bars():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_AAPL, params={"period": 3})

    for i, price in enumerate([100.0, 101.0, 99.0, 102.0, 103.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    value = registry.current_value(operand)
    assert value is not None
    assert isinstance(value, float)


def test_on_bar_only_updates_matching_bar_type():
    registry = IndicatorRegistry()
    aapl_operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_AAPL, params={"period": 2})
    msft_operand = IndicatorOperand(indicator="RSI", bar_type=BAR_TYPE_MSFT, params={"period": 2})

    for i, price in enumerate([100.0, 101.0, 99.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    assert registry.current_value(aapl_operand) is not None
    assert registry.current_value(msft_operand) is None


def test_ma_uses_required_ma_type_param():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(
        indicator="MA", bar_type=BAR_TYPE_AAPL, params={"period": 2, "ma_type": "SIMPLE"}
    )

    for i, price in enumerate([100.0, 102.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    assert registry.current_value(operand) == 101.0


def test_bollinger_bands_reads_selected_band():
    registry = IndicatorRegistry()
    upper_operand = IndicatorOperand(
        indicator="BB", bar_type=BAR_TYPE_AAPL, params={"period": 2, "k": 2.0, "band": "upper"}
    )
    lower_operand = IndicatorOperand(
        indicator="BB", bar_type=BAR_TYPE_AAPL, params={"period": 2, "k": 2.0, "band": "lower"}
    )

    for i, price in enumerate([100.0, 102.0, 104.0]):
        registry.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    upper = registry.current_value(upper_operand)
    lower = registry.current_value(lower_operand)
    assert upper is not None and lower is not None
    assert upper > lower


def test_obv_has_no_required_params():
    registry = IndicatorRegistry()
    operand = IndicatorOperand(indicator="OBV", bar_type=BAR_TYPE_AAPL, params={})

    registry.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert registry.current_value(operand) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indicator_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'condition_engine.indicator_registry'`

- [ ] **Step 3: Implement `condition_engine/indicator_registry.py`**

```python
# condition_engine/indicator_registry.py
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

    def get_or_create(self, operand: IndicatorOperand):
        key = self._key(operand)
        if key not in self._indicators:
            self._indicators[key] = _BUILDERS[operand.indicator](operand.params)
        return self._indicators[key]

    def on_bar(self, bar: Bar) -> None:
        bar_type_str = str(bar.bar_type)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indicator_registry.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add condition_engine/indicator_registry.py tests/test_indicator_registry.py
git commit -m "feat: add IndicatorRegistry wrapping nautilus_trader indicators"
```

---

### Task 3: `evaluator.py` — `ConditionEvaluator`

**Files:**
- Create: `condition_engine/evaluator.py`
- Test: `tests/test_condition_evaluator.py`

**Interfaces:**
- Consumes: `ConditionSet`/`Comparison`/`LiteralOperand`/`IndicatorOperand`
  (Task 1), `IndicatorRegistry` (Task 2, exact methods `on_bar`,
  `current_value`).
- Produces: `ConditionEvaluator(condition_set: ConditionSet, registry: IndicatorRegistry)`,
  `.on_bar(bar: Bar) -> None`, `.evaluate() -> bool`. No other code depends
  on this in this plan (later sub-projects consume it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_condition_evaluator.py
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import ConditionParser

BAR_TYPE_AAPL = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"
BAR_TYPE_MSFT = "MSFT.NASDAQ-1-MINUTE-LAST-EXTERNAL"


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


def test_uninitialized_indicator_evaluates_as_false_not_error():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "RSI", "bar_type": BAR_TYPE_AAPL, "params": {"period": 14}},
                    "op": "<",
                    "right": {"value": 30},
                }
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())

    assert evaluator.evaluate() is False


def test_and_combinator_requires_all_true():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": "<",
                    "right": {"value": -1000},
                },
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
    evaluator.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert evaluator.evaluate() is False


def test_or_combinator_requires_any_true():
    condition_set = ConditionParser.parse(
        {
            "combinator": "OR",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": "<",
                    "right": {"value": -1000},
                },
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
    evaluator.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    assert evaluator.evaluate() is True


def test_indicator_vs_indicator_golden_cross():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE_AAPL,
                        "params": {"period": 1, "ma_type": "SIMPLE"},
                    },
                    "op": ">",
                    "right": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE_AAPL,
                        "params": {"period": 2, "ma_type": "SIMPLE"},
                    },
                }
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
    for i, price in enumerate([100.0, 110.0]):
        evaluator.on_bar(_bar(BAR_TYPE_AAPL, price, i))

    assert evaluator.evaluate() is True


def test_multi_instrument_evaluates_using_last_known_value():
    condition_set = ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_AAPL, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
                {
                    "left": {"indicator": "OBV", "bar_type": BAR_TYPE_MSFT, "params": {}},
                    "op": ">=",
                    "right": {"value": 0},
                },
            ],
        }
    )
    evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())

    # Only AAPL ever receives a bar; MSFT's operand never initializes.
    evaluator.on_bar(_bar(BAR_TYPE_AAPL, 100.0, 0))

    # MSFT leg is still uninitialized (None) -> overall False, not an error,
    # and evaluate() returns immediately without waiting for an MSFT bar.
    assert evaluator.evaluate() is False

    evaluator.on_bar(_bar(BAR_TYPE_MSFT, 50.0, 1))

    # Now both legs have at least one bar each -> AAPL's last known value is
    # still used even though no new AAPL bar arrived in between.
    assert evaluator.evaluate() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_condition_evaluator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'condition_engine.evaluator'`

- [ ] **Step 3: Implement `condition_engine/evaluator.py`**

```python
# condition_engine/evaluator.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_condition_evaluator.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + this plan's 19 new tests)

- [ ] **Step 6: Commit**

```bash
git add condition_engine/evaluator.py tests/test_condition_evaluator.py
git commit -m "feat: add ConditionEvaluator gluing parser and indicator registry"
```

---

### Task 4: Update progress ledger and dispatch final review

**Files:** none (bookkeeping only)

- [ ] **Step 1: Append to the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 6: condition parser engine (spec 167a2cc, plan <this commit>) ---
Task 1: complete (condition_engine/parser.py, commit <hash>)
Task 2: complete (condition_engine/indicator_registry.py, commit <hash>)
Task 3: complete (condition_engine/evaluator.py, commit <hash>)
```

- [ ] **Step 2: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
right before Task 1 (the spec commit, `167a2cc`) as the base. Run
`scripts/review-package 167a2cc HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 6 complete.

## Out of scope (reminder, per spec)

Do not add: nested `AND`/`OR` trees, Nautilus `Strategy` auto-instantiation,
backtest automation/reporting, any dashboard/UI, or restrictions on mixing
markets within one condition set. These belong to later sub-projects.
