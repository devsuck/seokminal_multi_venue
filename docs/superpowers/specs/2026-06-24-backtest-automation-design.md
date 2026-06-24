# Backtest Automation + Sharpe/MDD Reporting (Sub-project 9)

**Goal:** A single function that, given an instrument, a date range, and a
sub-project-6/7-style condition+strategy JSON spec, runs an end-to-end
Nautilus backtest and returns Sharpe ratio / Max Drawdown / PnL — the
headless, API-first "run a backtest" entry point the eventual dashboard
backend will call, per the platform's standing Phase-1 architecture
requirements.

## Scope

In scope:
- One instrument (`AAPL.NASDAQ`, using sub-8's already-ingested catalog
  data — 250 daily bars, enough history for meaningful statistics).
- A single top-to-bottom function: catalog query -> `BacktestEngine`
  setup -> condition-gated strategy registration -> `engine.run()` ->
  Sharpe/MDD/PnL extraction, returned as a plain dict.
- One demo trading strategy: Nautilus's built-in
  `nautilus_trader.examples.strategies.ema_cross.EMACross`, wrapped to
  accept flat kwargs (see "Key Finding" below).
- Reuses sub-6 (`condition_engine`) and sub-7's
  (`strategy_spawner.spawner_parser.SpawnerParser`/`SpawnRule`) JSON
  condition+strategy schema unchanged for parsing the spawn-rule input.

Out of scope (deferred to later sub-projects):
- Multiple instruments/venues in one backtest run (single-instrument
  scope, same reasoning as every prior sub-project's "prove the pipeline
  on one symbol first" pattern).
- Live `TradingNode` execution — `BacktestEngine` only.
- Any new trading strategy logic beyond the `EMACross` wrapper — no
  custom indicators or signal logic written for this sub-project.
- Realistic IB-specific commission schedules or slippage models — uses
  Nautilus's built-in `FixedFeeModel`/`FillModel` with simple constants.
- Changes to `condition_engine` (sub-6) or `strategy_spawner.spawner_parser`
  (sub-7) — both consumed unmodified.

## Key Finding: `strategy_spawner.spawner.StrategySpawner` Does Not Work Inside a Running Backtest

Verified directly against the installed `nautilus_trader` (1.228.0) by
constructing a real `BacktestEngine`, registering one strategy, calling
`engine.run()`, and calling `engine.add_strategy(...)` from inside that
strategy's `on_bar` handler:

- `BacktestEngine.add_strategy(...)` while the trader is running logs
  `ERROR ... Cannot add a strategy to a running trader` and **does not
  raise** — the strategy silently never gets added. This reproduces
  identically with `streaming=True` batch-by-batch runs (the trader stays
  "RUNNING" between batches, so `add_strategy` is rejected there too).
  `add_strategy` only succeeds *between* separate `engine.run()` calls
  when the trader has fully stopped (confirmed: `run(end=t1)` then
  `add_strategy(...)` then `run(start=t1+1)` works) — but that requires
  re-running the entire engine in lockstep with every individual bar to
  catch each potential spawn point, which is both impractical (forces a
  separate `run()` call per bar instead of one continuous run) and not
  what sub-7's `StrategySpawner` was built or tested for (its own
  integration test only ever called `engine.add_strategy` *before*
  `engine.run()`, never during).

**Conclusion:** sub-7's `StrategySpawner` (the "dynamically call
`engine.add_strategy` once a condition fires" class) is not usable for a
single continuous backtest run. This sub-project does not modify or
deprecate `StrategySpawner` — it remains valid for whatever sub-7's own
scope was — but does not reuse it. Instead, this sub-project inverts the
control: every spawn-rule's strategy is registered with the engine
**before** `engine.run()` starts, wrapped in a gate that ignores bars
until its condition first evaluates true, then begins trading from that
bar onward — functionally equivalent spawn semantics (a strategy that
never trades until its condition fires, then trades with a cold/fresh
internal state from that point), achieved in a way that's actually
compatible with `BacktestEngine`'s one-shot `run()` model.

sub-7's `strategy_spawner.spawner_parser.SpawnerParser`/`SpawnRule` (the
JSON-parsing half, not the spawning half) is still reused unchanged — the
JSON schema and class/param resolution logic are unaffected by this
finding.

## Key Finding: Account Type and Missing Default Statistic

Also verified directly:
- A `CASH` account type rejects short-sell orders from a flat position
  (`SHORT SELLING not permitted on a CASH account`), which `EMACross`
  triggers on its sell-crossover signal when not already long. This
  sub-project uses `AccountType.MARGIN` for the venue instead.
- `nautilus_trader`'s `Portfolio` registers `SharpeRatio` by default but
  **not** `MaxDrawdown` (confirmed by reading
  `nautilus_trader/portfolio/portfolio.pyx`'s default-statistics list and
  by direct testing: `Max Drawdown` is absent from
  `analyzer.get_performance_stats_returns()` until
  `analyzer.register_statistic(MaxDrawdown())` is called explicitly
  before `calculate_statistics`). This sub-project registers it manually.

## Architecture

```
nautilus-multi-venue/
  backtest_runner/
    __init__.py
    ema_cross_flat.py     # EMACrossFlat(EMACross): flat-kwargs adapter
    gated_strategy.py      # make_gated_strategy_class(...) factory
    runner.py               # run_backtest(...) entry point
  tests/
    test_ema_cross_flat.py
    test_gated_strategy.py
    test_backtest_runner.py
```

### `backtest_runner/ema_cross_flat.py`

```python
class EMACrossFlat(EMACross):
    def __init__(self, **kwargs) -> None:
        config = EMACrossConfig(
            instrument_id=InstrumentId.from_str(kwargs["instrument_id"]),
            bar_type=BarType.from_str(kwargs["bar_type"]),
            trade_size=Decimal(str(kwargs["trade_size"])),
            fast_ema_period=kwargs.get("fast_ema_period", 10),
            slow_ema_period=kwargs.get("slow_ema_period", 20),
            request_bars=kwargs.get("request_bars", False),
            subscribe_trade_ticks=kwargs.get("subscribe_trade_ticks", False),
        )
        super().__init__(config)
```

- Satisfies sub-7's `strategy_class(**params)` contract (flat kwargs, JSON
  string fields converted to real `InstrumentId`/`BarType` objects —
  `EMACrossConfig` does **not** coerce strings to these types itself, so
  this conversion must happen here, confirmed by direct testing that
  passing a plain dict/string to `EMACrossConfig` produces an object whose
  `.fast_ema_period` etc. work but whose `instrument_id`/`bar_type` remain
  plain strings, which breaks `EMACross.on_start`'s `subscribe_bars` call).
- `request_bars=False`, `subscribe_trade_ticks=False` defaults: this
  backtest only has bar data in the catalog, not trade ticks, and we don't
  want `EMACross` requesting historical bars on start (no historical-data
  client configured for that request type in this minimal engine setup).

### `backtest_runner/gated_strategy.py`

```python
def make_gated_strategy_class(strategy_class: type, condition_set: ConditionSet) -> type:
    class _Gated(strategy_class):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
            self._armed = False

        def on_bar(self, bar) -> None:
            self._evaluator.on_bar(bar)
            if not self._armed:
                if not self._evaluator.evaluate():
                    return
                self._armed = True
            super().on_bar(bar)

    return _Gated
```

- `on_start` (and any other lifecycle hook) is inherited unchanged from
  `strategy_class` — subscriptions happen normally regardless of gate
  state, since the gate only needs to suppress *trading decisions*, not
  *data flow* (the condition's own indicators need bars to evaluate in the
  first place).
- Once `_armed` flips true, every subsequent bar (including the triggering
  one) is forwarded to `strategy_class.on_bar`, so the wrapped strategy's
  own indicators (e.g. `EMACross`'s fast/slow EMA) start warming up from
  that bar — a fresh start at the spawn point, matching sub-7's original
  one-shot/fresh-state spawn semantics.
- A dynamic subclass (not a fixed wrapper class storing an unregistered
  inner `Strategy` instance) because Nautilus `Strategy` instances must be
  the actual object registered with the `Trader`/kernel to receive proper
  `cache`/`msgbus` wiring — composing two separate `Strategy` objects
  (one outer, one inner) is not how Nautilus's registration model works.

### `backtest_runner/runner.py`

```python
def run_backtest(
    instrument_id: str,
    bar_type_str: str,
    start_ns: int,
    end_ns: int,
    catalog_path: str,
    spawn_rules_json: list[dict],
    starting_balance: float = 100_000,
) -> dict:
    ...
```

1. `ParquetDataCatalog(catalog_path).instruments(instrument_ids=[instrument_id])[0]`
   -> the stored `Equity` (no rebuilding via `build_us_equity`/
   `build_xkrx_equity` — query whatever's actually in the catalog, keeping
   this function venue-agnostic).
2. `catalog.bars(bar_types=[bar_type_str])`, filtered in Python to
   `start_ns <= bar.ts_event <= end_ns`. Raises `ValueError` if the
   filtered list is empty (never runs a backtest on no data).
3. `BacktestEngine()`; `engine.add_venue(venue=instrument.id.venue,
   oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
   starting_balances=[Money(starting_balance, instrument.quote_currency)],
   base_currency=instrument.quote_currency,
   fee_model=FixedFeeModel(Money(1, instrument.quote_currency)),
   fill_model=FillModel(prob_slippage=0.1))`.
4. `engine.portfolio.analyzer.register_statistic(MaxDrawdown())` (the
   missing-by-default statistic from the Key Finding above).
5. `engine.add_instrument(instrument)`; `engine.add_data(bars)`.
6. `rules = SpawnerParser.parse(spawn_rules_json)` (sub-7, unchanged).
7. For each rule: `gated_cls = make_gated_strategy_class(rule.strategy_class,
   rule.condition_set)`; `engine.add_strategy(gated_cls(**rule.params))`.
8. `engine.run()`.
9. `positions = engine.cache.positions()`;
   `account = engine.cache.account_for_venue(venue)`;
   `engine.portfolio.analyzer.calculate_statistics(account, positions)`.
10. Build and return:
    ```python
    {
        "instrument_id": instrument_id,
        "bar_count": len(bars),
        "sharpe_ratio": stats_returns.get("Sharpe Ratio (252 days)"),
        "max_drawdown": stats_returns.get("Max Drawdown"),
        "total_pnl": stats_pnls.get("PnL (total)"),
        "total_pnl_pct": stats_pnls.get("PnL% (total)"),
    }
    ```
    where `stats_returns = engine.portfolio.analyzer.get_performance_stats_returns()`
    and `stats_pnls = engine.portfolio.analyzer.get_performance_stats_pnls(instrument.quote_currency)`.

## Error Handling

- No bars found for the given instrument/bar_type/date range in the
  catalog -> `ValueError` with the instrument/range in the message, raised
  before any `BacktestEngine` is constructed.
- `spawn_rules_json` malformed -> whatever `ValueError` sub-7's
  `SpawnerParser.parse` already raises, propagated unmodified.
- A gated strategy's construction fails (e.g. `EMACrossFlat(**params)`
  missing a required key) -> propagates uncaught, at the point
  `gated_cls(**rule.params)` is called in `run_backtest` — never silently
  skipped.
- Any error from `engine.run()` itself (Nautilus-internal) -> propagates
  uncaught.

## Testing

- `tests/test_ema_cross_flat.py`: constructs `EMACrossFlat` with flat
  string/number kwargs, asserts the resulting strategy's `config.instrument_id`
  is a real `InstrumentId` (not a string) and `config.bar_type` is a real
  `BarType`, and that numeric fields round-trip correctly.
- `tests/test_gated_strategy.py`: a minimal dummy inner-strategy fixture
  (records every `on_bar` call it receives) wrapped via
  `make_gated_strategy_class`, fed bars where the condition starts false
  and later becomes true — asserts the inner strategy's `on_bar` is never
  called before the trigger bar and is called for every bar from the
  trigger bar onward (inclusive). Mirrors sub-6's
  `test_condition_evaluator.py` style (real `ConditionEvaluator`/
  `IndicatorRegistry`, no mocking of the condition-evaluation path).
- `tests/test_backtest_runner.py`: one integration test building a small
  synthetic bar series (written into a temp `ParquetDataCatalog`) with
  prices engineered so the spawn condition trips partway through, calling
  `run_backtest(...)` against the real `BacktestEngine`/`EMACrossFlat`,
  and asserting the returned dict has `sharpe_ratio`/`max_drawdown`/
  `total_pnl` keys present (not `None`) and `bar_count` matches the input.
- Manual end-to-end verification (not automated, mirrors sub-1/sub-8's
  pattern): run `run_backtest` against the real `AAPL.NASDAQ` data already
  in `./catalog` (sub-8) with a real `EMACrossFlat` spawn-rule JSON, and
  inspect the returned report for sane (non-NaN, non-`None`) values.

## Open Questions / Risks Carried Forward

- This sub-project's "gate" pattern works for `BacktestEngine`. Whether
  the same pattern (or sub-7's original dynamic-`add_strategy` approach)
  is appropriate for a future live `TradingNode` sub-project is an open
  question — `TradingNode` may have different rules around adding
  strategies while running. Re-verify directly against `TradingNode` when
  that sub-project starts; don't assume either pattern carries over.
- `FixedFeeModel`/`FillModel` constants ($1/trade, 10% slippage
  probability) are arbitrary placeholders chosen for "not literally zero,"
  not calibrated to any real venue's actual cost structure. Revisit if
  this report's numbers are ever used for a real capital-allocation
  decision rather than as a pipeline proof-of-concept.
