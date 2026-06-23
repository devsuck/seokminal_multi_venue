# Design: Quant Condition Parser Engine (Sub-project 6)

## Context

Sub-projects 1-5 built the Phase 1 broker/data foundation (KIS + IBKR data
feeds and order execution adapters). Sub-projects 4 and 5 are code-complete;
sub-project 4's final manual live-verification step is still pending (blocked
on KRX market hours, unrelated to this spec).

This sub-project starts Phase 2 of the user's roadmap: a user-defined
condition-expression engine that evaluates indicator-based trading
conditions (e.g. "RSI(14) < 30 AND MA(20) > MA(50)") against live/backtest
bar data. It does **not** yet wire into Nautilus `Strategy` auto-instantiation
or backtest automation/reporting — those are deferred to later sub-projects
(7+), per the roadmap's Phase 2 breakdown (parser → auto-strategy-spawn →
backtest automation+reporting).

## End-goal alignment

The user's stated long-term goal is a Bloomberg-Terminal-style platform
(dashboard, multiple bots, agentic AI trading, quant research tooling) on top
of this engine (see project memory `project-nautilus-platform-vision`).
Concretely for this spec:

- Conditions are expressed as **JSON**, not a custom string DSL. A future
  Phase 3 dashboard UI builder can generate this JSON directly, so the
  internal representation never needs to change when the UI layer is added.
- Evaluation is **incremental, per-bar** (`on_bar`), the same shape Nautilus
  `Strategy.on_bar` uses — this is the same code path for backtest and live,
  so Phase 4's agentic trading layer can reuse this engine unmodified rather
  than needing a separate live-evaluation rewrite.
- Multi-instrument, multi-timeframe conditions are supported from v1
  (needed for pairs trading / cross-asset correlation conditions, explicitly
  part of the platform vision's research-engine component).

## Decisions made during brainstorming

- **Representation**: JSON config, not a string DSL `(추천)(최종 목표에 적합)`
  — simpler to parse/validate, and a future UI builder produces this
  structure directly. Hand-authoring ergonomics are accepted as secondary
  since this will mostly be machine-generated later.
- **Evaluation model**: `on_bar` incremental update using Nautilus's
  existing indicator classes — confirmed all 6 requested indicators already
  exist in `nautilus_trader.indicators`: `RelativeStrengthIndex` (RSI),
  `MovingAverageFactory` (MA), `BollingerBands` (BB),
  `MovingAverageConvergenceDivergence` (MACD), `CommodityChannelIndex` (CCI),
  `OnBalanceVolume` (OBV). No indicator math is reimplemented.
- **Comparisons**: both indicator-vs-literal (`RSI < 30`) and
  indicator-vs-indicator (`MA(20) > MA(50)`, golden cross) are in scope.
- **Logical combination**: flat `AND`/`OR` only in v1 (a single combinator
  applied to a flat list of comparisons). Nested trees (`AND(OR(...), ...)`)
  are explicitly deferred to a later sub-project.
- **Multi-instrument/multi-timeframe**: supported from v1. Each operand
  carries its own `instrument_id` + `bar_type`, independent of the others in
  the same condition set.
- **Cross-instrument timing semantics**: when one operand's bar arrives and
  another operand (different instrument/timeframe) hasn't updated yet,
  evaluation uses **the last known value** for the stale operand rather than
  blocking until all operands have fresh data. Decided explicitly over
  waiting-for-sync, because: (a) in live trading, bars from different
  instruments/venues never arrive in lockstep even on the same exchange, and
  (b) KIS (KRX, 09:00-15:30 KST) and IBKR (US, ~22:30-05:00 KST) trading
  hours barely overlap, so a wait-for-both-fresh policy would leave
  cross-venue conditions evaluating almost never. Mixing markets in one
  condition set is explicitly **allowed**, not restricted.
- **No broker dependency**: this engine only consumes `Bar` objects and
  produces booleans — no KIS/IBKR client involved, so (unlike sub-projects
  4/5) there is no manual live-verification task gated on market hours. Full
  pytest coverage is the completion bar.

## Architecture

```
nautilus-multi-venue/
  condition_engine/
    parser.py              # ConditionParser: JSON -> ConditionSet tree
    indicator_registry.py  # IndicatorRegistry: keyed Nautilus indicator instances
    evaluator.py           # ConditionEvaluator: on_bar + evaluate()
  tests/
    test_condition_parser.py
    test_indicator_registry.py
    test_condition_evaluator.py
```

### `parser.py`

Dataclasses:
- `LiteralOperand(value: float)`
- `IndicatorOperand(indicator: str, instrument_id: str, bar_type: str, params: dict)`
- `Comparison(left: LiteralOperand | IndicatorOperand, op: str, right: LiteralOperand | IndicatorOperand)`
- `ConditionSet(combinator: Literal["AND", "OR"], comparisons: list[Comparison])`

`ConditionParser.parse(json_dict: dict) -> ConditionSet`. Raises
`ValueError` at parse time (not at evaluation time) for: unknown indicator
name (outside the 6 supported), unsupported `op` (only `<`, `<=`, `>`, `>=`,
`==` supported), missing required params for an indicator (e.g. RSI without
`period`), or unknown `combinator`.

Example input:

```json
{
  "combinator": "AND",
  "conditions": [
    {
      "left":  {"indicator": "RSI", "instrument_id": "AAPL.NASDAQ", "bar_type": "1-MINUTE", "params": {"period": 14}},
      "op": "<",
      "right": {"value": 30}
    },
    {
      "left":  {"indicator": "MA", "instrument_id": "AAPL.NASDAQ", "bar_type": "1-MINUTE", "params": {"period": 20}},
      "op": ">",
      "right": {"indicator": "MA", "instrument_id": "AAPL.NASDAQ", "bar_type": "1-MINUTE", "params": {"period": 50}}
    }
  ]
}
```

### `indicator_registry.py`

`IndicatorRegistry`:
- Internal map keyed by `(instrument_id, bar_type, indicator_name, tuple(sorted(params.items())))` -> Nautilus indicator instance.
- `get_or_create(operand: IndicatorOperand) -> Indicator` — lazily
  constructs the right Nautilus indicator via a small factory mapping
  (`RSI` -> `RelativeStrengthIndex`, `MA` -> `MovingAverageFactory.create`,
  `BB` -> `BollingerBands`, `MACD` -> `MovingAverageConvergenceDivergence`,
  `CCI` -> `CommodityChannelIndex`, `OBV` -> `OnBalanceVolume`).
- `on_bar(bar: Bar) -> None` — updates only the indicators keyed to
  `bar.instrument_id` + `bar.bar_type` (via each indicator's `handle_bar`).
  Indicators for other instruments/timeframes are untouched.
- `current_value(operand: IndicatorOperand) -> float | None` — returns the
  indicator's current value, or `None` if it hasn't warmed up yet (not yet
  `.initialized`).

### `evaluator.py`

`ConditionEvaluator(condition_set: ConditionSet, registry: IndicatorRegistry)`:
- `on_bar(bar: Bar) -> None` — delegates to `registry.on_bar(bar)`.
- `evaluate() -> bool` — resolves each `Comparison`'s left/right operand
  (literal value, or `registry.current_value(operand)`), applies `op`. If
  either side resolves to `None` (uninitialized indicator), that `Comparison`
  evaluates to `False` (not an exception — this is the expected state right
  after startup before indicators warm up). Combines all `Comparison` results
  with the `ConditionSet`'s `combinator` (`AND`/`OR`).

## Testing

- `test_condition_parser.py`: valid JSON -> correct tree; each error case
  (unknown indicator/op, missing params, unknown combinator) -> `ValueError`.
- `test_indicator_registry.py`: feed synthetic `Bar` sequences into real
  Nautilus indicator instances via `on_bar`; verify `.value`/`current_value`
  updates correctly and that bars for one `(instrument_id, bar_type)` key
  never affect indicators registered under a different key.
- `test_condition_evaluator.py`: AND/OR combination correctness; "not yet
  warmed up" (`None`) treated as `False`; multi-instrument case where only
  one operand's instrument receives a new bar still produces an immediate
  evaluation using the other operand's last known value (confirms the
  last-known-value semantics decided above).

No manual/live verification task — full pytest pass is the completion bar
for this sub-project, followed by the standard final whole-branch review.

## Out of scope (deferred to later sub-projects)

- Nested `AND`/`OR` condition trees (only flat combinator in v1).
- Auto-spawning a Nautilus `Strategy` instance when a condition is met
  (Phase 2, next sub-project).
- Backtest automation pipeline + performance reporting (Sharpe, MDD)
  (Phase 2, after auto-strategy-spawn).
- Any dashboard/UI for authoring conditions (Phase 3).
- Restricting or warning on cross-market condition sets — explicitly allowed
  per the decision above, not a restriction to add later.
