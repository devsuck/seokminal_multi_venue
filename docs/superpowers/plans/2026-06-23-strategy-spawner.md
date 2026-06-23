# Strategy Spawner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `strategy_spawner/`, which parses a JSON list pairing
sub-project 6 `condition` blocks with `strategy` (class + fixed params)
blocks, and auto-instantiates each Strategy into a `BacktestEngine` the
first time its condition evaluates true.

**Architecture:** Two single-responsibility modules. `spawner_parser.py`
turns the JSON list into a list of `SpawnRule` dataclasses, reusing
`condition_engine.parser.ConditionParser` unchanged for the condition half
and resolving/validating the `strategy.class` import path itself.
`spawner.py`'s `StrategySpawner` owns one `ConditionEvaluator` (sub-6) per
rule, forwards every bar to all of them via `on_bar`, and after each bar
checks not-yet-spawned rules: the first time a rule's `evaluate()` returns
`True`, it builds `strategy_class(**params)` and calls
`engine.add_strategy(...)`, then marks that rule spawned permanently
(one-shot, never re-checked).

**Tech Stack:** `nautilus_trader` (already a dependency) — specifically
`nautilus_trader.trading.strategy.Strategy`,
`nautilus_trader.backtest.engine.BacktestEngine`,
`nautilus_trader.model.data.Bar`. `condition_engine` (sub-project 6, already
in this repo) — `condition_engine.parser.ConditionParser`,
`condition_engine.evaluator.ConditionEvaluator`,
`condition_engine.indicator_registry.IndicatorRegistry`. `importlib`
(stdlib) for dynamic class loading. `pytest` (already configured).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-23-strategy-spawner-design.md`.
- JSON spec is a top-level **list** of rule dicts, each
  `{"condition": {...sub-6 schema...}, "strategy": {"class": "module.path:ClassName", "params": {...}}}`.
- `strategy.class` uses a colon separator between module path and class
  name (e.g. `"my_strategies.mean_reversion:MeanReversionStrategy"`), split
  on the **last** `:`.
- `condition` blocks are parsed by `condition_engine.parser.ConditionParser.parse`
  unmodified — no changes to `condition_engine` in this plan.
- Resolved `strategy.class` must satisfy
  `issubclass(cls, nautilus_trader.trading.strategy.Strategy)`, checked at
  parse time.
- `strategy.params` is forwarded as `**params` to the resolved class's
  constructor with **no key validation** at parse time (no fixed
  whitelist exists for arbitrary Strategy classes, unlike condition_engine's
  6-indicator list) — bad params surface only at spawn time as whatever
  error the constructor raises, uncaught.
- One-shot semantics only: each rule's Strategy is instantiated at most
  once per `StrategySpawner` instance. No edge-detection, no re-arming, no
  Strategy removal/lifecycle management.
- Each rule owns its own fresh `IndicatorRegistry` (no sharing across
  rules).
- Targets `nautilus_trader.backtest.engine.BacktestEngine` only — no
  `TradingNode`/live wiring in this plan.
- All parse-time validation errors are raised as `ValueError` (chaining the
  original exception via `from exc` where one exists), matching
  `condition_engine`'s existing contract.
- No nested condition trees, no dynamic param injection from triggering
  bar/indicator values, no Strategy-class whitelist, no backtest run
  orchestration or performance reporting — all out of scope per spec.
- Verified directly against the installed `nautilus_trader` library in this
  environment (not assumed from docs):
  - `BacktestEngine()` constructs with no required arguments and is fully
    `READY` immediately (no venue/instrument registration needed before
    calling `add_strategy`).
  - `BacktestEngine.add_strategy(self, strategy: Strategy) -> None` accepts
    a bare `Strategy` instance and registers it on the engine's trader
    (confirmed via `engine.trader.strategy_states()` showing the new
    strategy as `READY` immediately after `add_strategy`).
  - `nautilus_trader.trading.strategy.Strategy()` constructs with zero
    arguments (base class has no required `config`), so a minimal test
    subclass with its own `__init__(self, **kwargs)` is a valid spawn
    target.

---

### Task 1: `spawner_parser.py` — JSON to `SpawnRule` list

**Files:**
- Create: `strategy_spawner/__init__.py` (empty)
- Create: `strategy_spawner/spawner_parser.py`
- Test: `tests/test_spawner_parser.py`

**Interfaces:**
- Consumes: `condition_engine.parser.ConditionParser.parse(dict) -> ConditionSet`
  (sub-project 6, unmodified).
- Produces (consumed by Task 2):
  - `SpawnRule(condition_set: ConditionSet, strategy_class: type, params: dict)`
    — frozen dataclass.
  - `SpawnerParser.parse(json_list: list[dict]) -> list[SpawnRule]`
    (staticmethod).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spawner_parser.py
import pytest

from condition_engine.parser import ConditionSet
from strategy_spawner.spawner_parser import SpawnerParser, SpawnRule

BAR_TYPE = "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL"


def _condition_dict():
    return {
        "combinator": "AND",
        "conditions": [
            {
                "left": {"indicator": "RSI", "bar_type": BAR_TYPE, "params": {"period": 14}},
                "op": "<",
                "right": {"value": 30},
            }
        ],
    }


def test_parse_single_valid_rule():
    rules = SpawnerParser.parse(
        [
            {
                "condition": _condition_dict(),
                "strategy": {
                    "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                    "params": {"trade_size": 100},
                },
            }
        ]
    )

    assert len(rules) == 1
    rule = rules[0]
    assert isinstance(rule, SpawnRule)
    assert isinstance(rule.condition_set, ConditionSet)
    from tests.fixtures.dummy_strategy import DummyStrategy

    assert rule.strategy_class is DummyStrategy
    assert rule.params == {"trade_size": 100}


def test_parse_multiple_rules():
    rules = SpawnerParser.parse(
        [
            {
                "condition": _condition_dict(),
                "strategy": {
                    "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                    "params": {"trade_size": 100},
                },
            },
            {
                "condition": _condition_dict(),
                "strategy": {
                    "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                    "params": {"trade_size": 200},
                },
            },
        ]
    )

    assert len(rules) == 2
    assert rules[0].params == {"trade_size": 100}
    assert rules[1].params == {"trade_size": 200}


def test_parse_delegates_condition_errors_to_condition_parser():
    with pytest.raises(ValueError, match="combinator"):
        SpawnerParser.parse(
            [
                {
                    "condition": {"combinator": "XOR", "conditions": []},
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:DummyStrategy",
                        "params": {},
                    },
                }
            ]
        )


def test_parse_rejects_malformed_class_string():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {"class": "no-colon-here", "params": {}},
                }
            ]
        )


def test_parse_rejects_unimportable_module():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {"class": "nonexistent.module:Foo", "params": {}},
                }
            ]
        )


def test_parse_rejects_missing_class_in_module():
    with pytest.raises(ValueError, match="class"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:NoSuchClass",
                        "params": {},
                    },
                }
            ]
        )


def test_parse_rejects_non_strategy_class():
    with pytest.raises(ValueError, match="Strategy"):
        SpawnerParser.parse(
            [
                {
                    "condition": _condition_dict(),
                    "strategy": {
                        "class": "tests.fixtures.dummy_strategy:NotAStrategy",
                        "params": {},
                    },
                }
            ]
        )
```

- [ ] **Step 2: Create the shared test fixture module**

```python
# tests/fixtures/__init__.py
```

(empty file)

```python
# tests/fixtures/dummy_strategy.py
from nautilus_trader.trading.strategy import Strategy


class DummyStrategy(Strategy):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs


class NotAStrategy:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_spawner_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'strategy_spawner'`

- [ ] **Step 4: Implement `strategy_spawner/spawner_parser.py`**

```python
# strategy_spawner/spawner_parser.py
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
        condition_set = ConditionParser.parse(entry["condition"])
        strategy_class = SpawnerParser._resolve_strategy_class(
            entry["strategy"]["class"]
        )
        params = entry["strategy"].get("params", {})
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_spawner_parser.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add strategy_spawner/__init__.py strategy_spawner/spawner_parser.py \
  tests/fixtures/__init__.py tests/fixtures/dummy_strategy.py tests/test_spawner_parser.py
git commit -m "feat: add SpawnerParser for JSON condition+strategy spawn rules"
```

---

### Task 2: `spawner.py` — `StrategySpawner`

**Files:**
- Create: `strategy_spawner/spawner.py`
- Test: `tests/test_spawner.py`

**Interfaces:**
- Consumes: `SpawnRule` (Task 1, exact fields `condition_set`,
  `strategy_class`, `params`); `condition_engine.evaluator.ConditionEvaluator`
  and `condition_engine.indicator_registry.IndicatorRegistry` (sub-project
  6, exact methods `on_bar(bar)`, `evaluate() -> bool`).
- Produces: `StrategySpawner(rules: list[SpawnRule], engine)`,
  `.on_bar(bar: Bar) -> None`, `.spawned_count -> int` property. `engine`
  is any object exposing `add_strategy(strategy) -> None` (a real
  `BacktestEngine` in Task 3's integration test, a recording stub in this
  task's unit tests).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spawner.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_spawner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'strategy_spawner.spawner'`

- [ ] **Step 3: Implement `strategy_spawner/spawner.py`**

```python
# strategy_spawner/spawner.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_spawner.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add strategy_spawner/spawner.py tests/test_spawner.py
git commit -m "feat: add StrategySpawner with one-shot condition-triggered spawning"
```

---

### Task 3: Integration test against a real `BacktestEngine`

**Files:**
- Test: `tests/test_spawner_integration.py`

**Interfaces:**
- Consumes: `StrategySpawner`, `SpawnRule` (Task 2), a real
  `nautilus_trader.backtest.engine.BacktestEngine`. No new production code.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spawner_integration.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spawner_integration.py -v`
Expected: FAIL (test file doesn't exist yet, collection error) — this is
the first run, since no production code changes are needed for this task.

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_spawner_integration.py -v`
Expected: 1 passed (no implementation changes needed — Task 2's
`StrategySpawner` already supports any `add_strategy`-compatible engine)

- [ ] **Step 4: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + this plan's 12 new tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_spawner_integration.py
git commit -m "test: verify StrategySpawner against a real BacktestEngine"
```

---

### Task 4: Update progress ledger and dispatch final review

**Files:** none (bookkeeping only)

- [ ] **Step 1: Append to the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 7: strategy spawner (spec 71ca66b, plan <this commit>) ---
Task 1: complete (strategy_spawner/spawner_parser.py, commit <hash>)
Task 2: complete (strategy_spawner/spawner.py, commit <hash>)
Task 3: complete (tests/test_spawner_integration.py, commit <hash>)
```

- [ ] **Step 2: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
right before Task 1 (the spec commit, `71ca66b`) as the base. Run
`scripts/review-package 71ca66b HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 7 complete.

## Out of scope (reminder, per spec)

Do not add: live `TradingNode`/KIS/IB wiring, dynamic param injection from
triggering bar/indicator values, edge-triggered re-spawn, Strategy
removal/lifecycle management, a Strategy-class whitelist, backtest run
orchestration, or performance reporting (Sharpe/MDD). These belong to
sub-project 8 or later.
