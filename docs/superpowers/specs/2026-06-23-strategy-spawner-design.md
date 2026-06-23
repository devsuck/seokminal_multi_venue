# Strategy Spawner Design (Sub-project 7)

**Goal:** Auto-instantiate a Nautilus `Strategy` into a `BacktestEngine` the
moment a JSON-configured condition (built on sub-project 6's
`condition_engine`) becomes true, using fixed parameters declared up front.
This is Phase 2 of the platform roadmap, narrowed to just the "condition ->
auto Strategy spawn" half; backtest run automation and performance reporting
(Sharpe/MDD) are deferred to sub-project 8.

## Scope

In scope:
- A JSON spec format that pairs one sub-6 `condition` block with one
  `strategy` block (`class` import path + fixed `params`).
- Parsing that JSON into validated `SpawnRule` objects, reusing
  `condition_engine.parser.ConditionParser` unchanged.
- A `StrategySpawner` that feeds bars to per-rule `ConditionEvaluator`s and,
  the first time a rule's condition evaluates true, instantiates its
  `Strategy` class with its fixed params and calls
  `BacktestEngine.add_strategy(...)`.
- One-shot semantics: each rule spawns at most once per `StrategySpawner`
  lifetime. No re-arming, no edge-detection beyond "first time true."

Out of scope (explicitly deferred):
- Live `TradingNode` / KIS / IB wiring (sub-project 8+). This sub-project
  only targets `BacktestEngine`.
- Dynamic param injection from the triggering bar/indicator value. All
  `strategy.params` are fixed literals taken verbatim from the JSON.
- Edge-triggered re-spawn (false -> true -> false -> true spawning again),
  Strategy removal/stopping, or any other Strategy lifecycle management
  beyond what Nautilus itself does once a Strategy is added.
- Backtest execution, run orchestration, or performance reporting
  (Sharpe/MDD) — sub-project 8.
- Nested condition trees, new indicators, or any other condition_engine
  scope already excluded by sub-project 6's spec.
- A pre-built whitelist of allowed Strategy classes — any importable class
  that is a `nautilus_trader.trading.strategy.Strategy` subclass is
  accepted, since this is a backtest-only tool operating on
  developer-authored config, not an untrusted-input boundary.

## JSON Spec Format

A top-level list of spawn rules:

```json
[
  {
    "condition": {
      "combinator": "AND",
      "conditions": [
        {
          "left": {"indicator": "RSI", "bar_type": "AAPL.NASDAQ-1-MINUTE-LAST-EXTERNAL", "params": {"period": 14}},
          "op": "<",
          "right": {"value": 30}
        }
      ]
    },
    "strategy": {
      "class": "my_strategies.mean_reversion:MeanReversionStrategy",
      "params": {"instrument_id": "AAPL.NASDAQ", "trade_size": 100}
    }
  }
]
```

- `condition` is passed through verbatim to
  `ConditionParser.parse(condition_dict)` — same schema, same validation,
  same supported indicators/ops/combinator as sub-project 6. No changes to
  `condition_engine` itself.
- `strategy.class` is a `"module.path:ClassName"` string (colon separator,
  consistent with Python's own `importlib.metadata` entry-point convention
  and unambiguous when the module path itself contains dots).
- `strategy.params` is an opaque dict forwarded as `**params` to the
  Strategy's constructor. Not validated by this sub-project (see Error
  Handling).

## Components

### `strategy_spawner/spawner_parser.py`

```python
@dataclass(frozen=True)
class SpawnRule:
    condition_set: ConditionSet         # from condition_engine.parser
    strategy_class: type                # resolved, validated Strategy subclass
    params: dict

class SpawnerParser:
    @staticmethod
    def parse(json_list: list[dict]) -> list[SpawnRule]: ...
```

- For each entry: `ConditionParser.parse(entry["condition"])` builds the
  `ConditionSet` (reuses sub-6 validation as-is).
- `entry["strategy"]["class"]` is split on the last `:`; module is imported
  via `importlib.import_module`, class resolved via `getattr`. Any failure
  (bad format, `ModuleNotFoundError`, `AttributeError`) is caught and
  re-raised as `ValueError` with the original exception chained (`raise ...
  from exc`), matching sub-6's "always `ValueError` at parse time" contract.
- Resolved class must satisfy
  `issubclass(cls, nautilus_trader.trading.strategy.Strategy)`; otherwise
  `ValueError`.
- `entry["strategy"]["params"]` is taken as-is, no key validation.

### `strategy_spawner/spawner.py`

```python
class StrategySpawner:
    def __init__(self, rules: list[SpawnRule], engine: BacktestEngine) -> None: ...
    def on_bar(self, bar: Bar) -> None: ...

    @property
    def spawned_count(self) -> int: ...
```

- Constructor builds one `(ConditionEvaluator, spawned: bool)` pair per
  rule, each evaluator owning its own fresh `IndicatorRegistry` (no sharing
  across rules — matches sub-6's per-evaluator ownership model, keeps each
  rule independently testable, and the duplicated indicator computation is
  negligible at this scale).
- `on_bar(bar)`: forwards `bar` to every rule's evaluator
  (`evaluator.on_bar(bar)`), unconditionally — even already-spawned rules,
  so their evaluators stay consistent if ever inspected, though their
  result is never acted on again.
- After forwarding, iterates not-yet-spawned rules; if
  `evaluator.evaluate()` is `True`, instantiates
  `rule.strategy_class(**rule.params)`, calls
  `self._engine.add_strategy(instance)`, and marks that rule spawned. This
  check happens once per `on_bar` call, after the bar has been applied to
  every evaluator (so a rule that needs this exact bar to first initialize
  its indicators is correctly evaluated against post-bar state).
- No `try/except` around the spawn call: if `strategy_class(**params)` or
  `add_strategy` raises, it propagates immediately and uncaught. A
  misconfigured rule means the whole spawner run is misconfigured; failing
  loudly is safer than silently skipping a rule the user expected to fire.

## Error Handling

All `SpawnRule` validation happens eagerly in `SpawnerParser.parse`, never
deferred to `on_bar`/spawn time — same principle as sub-6:

- Invalid `condition` block -> whatever `ValueError` sub-6's
  `ConditionParser.parse` already raises, unmodified, propagated as-is.
- Malformed `strategy.class` string, import failure, or resolved object not
  a `Strategy` subclass -> `ValueError` raised by `SpawnerParser`, with the
  original exception chained via `from exc` where applicable.
- `strategy.params` content is intentionally *not* validated at parse time
  (no per-class required-param list exists, unlike condition_engine's fixed
  6-indicator whitelist) — bad params surface as whatever error the
  Strategy's own `__init__` raises, at spawn time, uncaught.

## Testing

Following sub-6's convention: `pytest`, verify directly against the
installed `nautilus_trader` library, minimal mocking.

- `tests/test_spawner_parser.py`: valid parse round-trip; condition-side
  errors delegate correctly to `ConditionParser`; bad `class` string format
  rejected; import failure (`ModuleNotFoundError`/`AttributeError`)
  rejected; resolved-but-non-`Strategy` class rejected. Uses one minimal
  dummy `Strategy` subclass defined in the test module as the "valid"
  target class.
- `tests/test_spawner.py`: using a stub object with a recording
  `add_strategy(self, strategy)` method (not a full `BacktestEngine`, to
  keep these tests fast and focused) —
  1. condition never true -> never spawns.
  2. condition becomes true -> spawns exactly once, with the exact
     `params` from the rule.
  3. further bars after spawning -> no second spawn (one-shot).
  4. two rules, only one's condition true -> only that one spawns, the
     other is unaffected.
- One integration test in `tests/test_spawner.py` (or a separate
  `tests/test_spawner_integration.py`) using a real
  `nautilus_trader.backtest.engine.BacktestEngine` instance, confirming
  `add_strategy` actually accepts and registers the spawned Strategy
  end-to-end — mirrors sub-6's "verified directly against the installed
  library" requirement.

## Open Questions / Risks Carried Forward

- Sub-6's final review noted that `IndicatorRegistry`'s buffer-clear
  optimization assumes operands are evaluated before steady-state; since
  `StrategySpawner` constructs each rule's evaluator once up front (no
  mid-stream addition), this is not a concern here.
- No whitelist on Strategy classes is a deliberate choice for this
  backtest-only, developer-authored-config context; if this spawner is ever
  reused for a less trusted input path (e.g. a future dashboard letting
  end users submit JSON), that decision must be revisited.
