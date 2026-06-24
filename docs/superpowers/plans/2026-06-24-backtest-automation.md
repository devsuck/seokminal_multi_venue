# Backtest Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `backtest_runner/`, a single `run_backtest(...)` function
that queries an instrument's bars from the existing `ParquetDataCatalog`,
runs a Nautilus `BacktestEngine` with condition-gated strategies, and
returns Sharpe ratio / Max Drawdown / PnL as a plain dict.

**Architecture:** Three files. `ema_cross_flat.py` adapts Nautilus's
built-in `EMACross` example strategy to sub-7's flat-kwargs constructor
contract. `gated_strategy.py`'s `make_gated_strategy_class` factory builds
a dynamic subclass of any flat-kwargs strategy class that ignores bars
until its sub-6 `ConditionSet` first evaluates true, then trades normally
from that bar onward — registered with the engine from the start (Nautilus
does not support adding strategies to a running `BacktestEngine`, confirmed
directly against the installed library; see spec's "Key Finding"). `runner.py`
wires catalog query, venue/engine setup, sub-7's `SpawnerParser` for
condition+strategy JSON, gated-strategy registration, `engine.run()`, and
performance-stat extraction into one function.

**Tech Stack:** `nautilus_trader` (already a dependency) —
`nautilus_trader.backtest.engine.BacktestEngine`,
`nautilus_trader.backtest.models.{FixedFeeModel, FillModel}`,
`nautilus_trader.analysis.MaxDrawdown`,
`nautilus_trader.examples.strategies.ema_cross.{EMACross, EMACrossConfig}`,
`nautilus_trader.persistence.catalog.ParquetDataCatalog`. `condition_engine`
(sub-6) and `strategy_spawner.spawner_parser` (sub-7), both already in this
repo, reused unchanged. `pytest` (already configured).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-24-backtest-automation-design.md`.
- Single instrument scope: `AAPL.NASDAQ`, using sub-8's already-ingested
  catalog data.
- `BacktestEngine.add_strategy(...)` does not work once the trader is
  running (confirmed: logs `ERROR ... Cannot add a strategy to a running
  trader` and silently fails, no exception raised) — every spawn-rule's
  strategy must be registered **before** `engine.run()` starts, wrapped via
  `make_gated_strategy_class` so it stays dormant until its condition fires.
  Do not attempt to call `engine.add_strategy` mid-run anywhere in this plan.
- Venue uses `AccountType.MARGIN`, not `CASH` (`CASH` rejects short-sell
  orders from a flat position, which `EMACross`'s sell-crossover signal
  triggers).
- `MaxDrawdown` is **not** registered by default on
  `engine.portfolio.analyzer` — must call
  `engine.portfolio.analyzer.register_statistic(MaxDrawdown())` explicitly
  before `calculate_statistics`, or `"Max Drawdown"` will be absent from
  `get_performance_stats_returns()`.
- `EMACrossConfig` does not coerce plain strings to `InstrumentId`/`BarType`
  — `EMACrossFlat` must convert them explicitly via
  `InstrumentId.from_str(...)`/`BarType.from_str(...)` before constructing
  the config, or `EMACross.on_start`'s `subscribe_bars` call breaks.
- `condition_engine` (sub-6) and `strategy_spawner.spawner_parser` (sub-7)
  are consumed unchanged — no edits to either in this plan.
- No multiple instruments/venues per run, no live `TradingNode`, no new
  trading-strategy logic beyond the `EMACross` wrapper, no realistic
  IB-specific commission schedules — all deferred per spec's "Out of scope".
- Verified directly against the installed `nautilus_trader` (1.228.0) in
  this environment (not assumed from docs):
  - `BacktestEngine()` constructs with no required args;
    `engine.add_venue(venue, oms_type=OmsType.NETTING,
    account_type=AccountType.MARGIN, starting_balances=[Money(...)],
    base_currency=..., fee_model=FixedFeeModel(Money(1, currency)),
    fill_model=FillModel(prob_slippage=0.1))` succeeds.
  - `ParquetDataCatalog.instruments(instrument_ids=[str])` and
    `ParquetDataCatalog.bars(bar_types=[str])` both work as documented,
    confirmed against the real `./catalog` data from sub-8 (250 AAPL bars
    returned for `bar_types=["AAPL.NASDAQ-1-DAY-LAST-EXTERNAL"]`).
  - `engine.cache.account_for_venue(venue)` and `engine.cache.positions()`
    both work as the inputs to
    `engine.portfolio.analyzer.calculate_statistics(account, positions)`.
  - A full synthetic run (10 bars, a `MA(2) > 80` condition that trips
    after bar 2, `EMACrossFlat` with `fast_ema_period=1,
    slow_ema_period=2`) was run end-to-end directly in this environment:
    the gate correctly suppressed trading until the trigger bar, exactly
    one position was opened after that point, and
    `get_performance_stats_returns()` /
    `get_performance_stats_pnls(currency)` both returned populated dicts
    with `"Sharpe Ratio (252 days)"`, `"Max Drawdown"`, `"PnL (total)"`,
    `"PnL% (total)"` keys present.
  - Even with zero trades in a run, all of the above statistic keys are
    still present in the returned dicts (value `nan` rather than the key
    being absent, except `"Max Drawdown"` and `"PnL (total)"`/`"PnL% (total)"`
    which are `0.0`) — confirmed directly, so no test needs to special-case
    a "key missing" scenario.

---

### Task 1: `EMACrossFlat`

**Files:**
- Create: `backtest_runner/__init__.py` (empty)
- Create: `backtest_runner/ema_cross_flat.py`
- Test: `tests/test_ema_cross_flat.py`

**Interfaces:**
- Consumes: nothing from other tasks (uses only
  `nautilus_trader.examples.strategies.ema_cross.{EMACross, EMACrossConfig}`).
- Produces (consumed by Task 3): `EMACrossFlat(**kwargs)` — a
  `nautilus_trader.trading.strategy.Strategy` subclass accepting flat
  kwargs: `instrument_id: str`, `bar_type: str`, `trade_size` (int/str/
  Decimal-coercible), `fast_ema_period: int` (default 10),
  `slow_ema_period: int` (default 20), `request_bars: bool` (default
  `False`), `subscribe_trade_ticks: bool` (default `False`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ema_cross_flat.py
from decimal import Decimal

from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from backtest_runner.ema_cross_flat import EMACrossFlat


def test_ema_cross_flat_converts_flat_kwargs_to_config():
    strategy = EMACrossFlat(
        instrument_id="AAPL.NASDAQ",
        bar_type="AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
        trade_size=10,
        fast_ema_period=3,
        slow_ema_period=5,
    )

    assert strategy.config.instrument_id == InstrumentId.from_str("AAPL.NASDAQ")
    assert strategy.config.bar_type == BarType.from_str("AAPL.NASDAQ-1-DAY-LAST-EXTERNAL")
    assert strategy.config.trade_size == Decimal("10")
    assert strategy.config.fast_ema_period == 3
    assert strategy.config.slow_ema_period == 5
    assert strategy.config.request_bars is False
    assert strategy.config.subscribe_trade_ticks is False


def test_ema_cross_flat_uses_default_periods_when_omitted():
    strategy = EMACrossFlat(
        instrument_id="AAPL.NASDAQ",
        bar_type="AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
        trade_size=10,
    )

    assert strategy.config.fast_ema_period == 10
    assert strategy.config.slow_ema_period == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ema_cross_flat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest_runner'`

- [ ] **Step 3: Implement `backtest_runner/ema_cross_flat.py`**

```python
# backtest_runner/ema_cross_flat.py
from decimal import Decimal

from nautilus_trader.examples.strategies.ema_cross import EMACross, EMACrossConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ema_cross_flat.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backtest_runner/__init__.py backtest_runner/ema_cross_flat.py tests/test_ema_cross_flat.py
git commit -m "feat: add EMACrossFlat flat-kwargs adapter for EMACross"
```

---

### Task 2: `make_gated_strategy_class`

**Files:**
- Create: `backtest_runner/gated_strategy.py`
- Test: `tests/test_gated_strategy.py`

**Interfaces:**
- Consumes: `condition_engine.parser.ConditionSet` (sub-6, unmodified),
  `condition_engine.evaluator.ConditionEvaluator`,
  `condition_engine.indicator_registry.IndicatorRegistry` (sub-6,
  unmodified, exact methods `on_bar(bar)`, `evaluate() -> bool`).
- Produces (consumed by Task 3): `make_gated_strategy_class(strategy_class:
  type, condition_set: ConditionSet) -> type`. The returned class accepts
  the same `**kwargs` constructor as `strategy_class` and behaves
  identically once its condition has evaluated true at least once;
  before that, its `on_bar` is a no-op for the wrapped strategy (but still
  updates the gate's own condition-evaluation state).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gated_strategy.py
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from backtest_runner.gated_strategy import make_gated_strategy_class
from condition_engine.parser import ConditionParser

BAR_TYPE = "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL"


class DummyInnerStrategy(Strategy):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs
        self.bars_seen: list = []

    def on_bar(self, bar) -> None:
        self.bars_seen.append(bar)


def _bar(price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(BAR_TYPE),
        open=Price.from_str(f"{price}.00"),
        high=Price.from_str(f"{price + 1}.00"),
        low=Price.from_str(f"{price - 1}.00"),
        close=Price.from_str(f"{price}.00"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def _ma_above_80_condition():
    return ConditionParser.parse(
        {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {
                        "indicator": "MA",
                        "bar_type": BAR_TYPE,
                        "params": {"period": 2, "ma_type": "SIMPLE"},
                    },
                    "op": ">",
                    "right": {"value": 80},
                }
            ],
        }
    )


def test_gated_strategy_suppresses_on_bar_before_condition_true():
    gated_cls = make_gated_strategy_class(DummyInnerStrategy, _ma_above_80_condition())
    strategy = gated_cls()

    strategy.on_bar(_bar(50, 0))
    strategy.on_bar(_bar(50, 1))

    assert strategy.bars_seen == []


def test_gated_strategy_forwards_on_bar_from_trigger_bar_onward():
    gated_cls = make_gated_strategy_class(DummyInnerStrategy, _ma_above_80_condition())
    strategy = gated_cls()

    bar0 = _bar(50, 0)
    bar1 = _bar(50, 1)
    bar2 = _bar(100, 2)  # MA(2) of [50, 100] = 75, still <= 80
    bar3 = _bar(100, 3)  # MA(2) of [100, 100] = 100, > 80 -> trigger here
    bar4 = _bar(100, 4)

    for bar in [bar0, bar1, bar2, bar3, bar4]:
        strategy.on_bar(bar)

    assert strategy.bars_seen == [bar3, bar4]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gated_strategy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest_runner.gated_strategy'`

- [ ] **Step 3: Implement `backtest_runner/gated_strategy.py`**

```python
# backtest_runner/gated_strategy.py
from nautilus_trader.model.data import Bar

from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import ConditionSet


def make_gated_strategy_class(strategy_class: type, condition_set: ConditionSet) -> type:
    class _Gated(strategy_class):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._evaluator = ConditionEvaluator(condition_set, IndicatorRegistry())
            self._armed = False

        def on_bar(self, bar: Bar) -> None:
            self._evaluator.on_bar(bar)
            if not self._armed:
                if not self._evaluator.evaluate():
                    return
                self._armed = True
            super().on_bar(bar)

    return _Gated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gated_strategy.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backtest_runner/gated_strategy.py tests/test_gated_strategy.py
git commit -m "feat: add make_gated_strategy_class for condition-gated strategy spawning"
```

---

### Task 3: `run_backtest`

**Files:**
- Create: `backtest_runner/runner.py`
- Test: `tests/test_backtest_runner.py`

**Interfaces:**
- Consumes: `EMACrossFlat` (Task 1, used only by the test's JSON spec, not
  imported directly by `runner.py`); `make_gated_strategy_class` (Task 2);
  `strategy_spawner.spawner_parser.SpawnerParser.parse(list[dict]) ->
  list[SpawnRule]` (sub-7, exact fields `condition_set`, `strategy_class`,
  `params`); `nautilus_trader.persistence.catalog.ParquetDataCatalog`.
- Produces: `run_backtest(instrument_id: str, bar_type_str: str, start_ns:
  int, end_ns: int, catalog_path: str, spawn_rules_json: list[dict],
  starting_balance: float = 100_000) -> dict` with keys `instrument_id`,
  `bar_count`, `sharpe_ratio`, `max_drawdown`, `total_pnl`,
  `total_pnl_pct`. No other task in this plan depends on this.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest_runner.py
import tempfile

import pytest
from nautilus_trader.model.data import Bar
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_us_equity
from backtest_runner.runner import run_backtest


def _bar(bar_type, price: float, ts: int) -> Bar:
    return Bar(
        bar_type=bar_type,
        open=Price.from_str(f"{price}.00"),
        high=Price.from_str(f"{price + 1}.00"),
        low=Price.from_str(f"{price - 1}.00"),
        close=Price.from_str(f"{price}.00"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_run_backtest_returns_report_with_expected_keys():
    instrument = build_us_equity("AAPL")
    bar_type = bar_type_for(instrument.id)
    bar_type_str = str(bar_type)

    prices = [50, 50, 100, 100, 100, 100, 100, 100, 100, 100]
    bars = [_bar(bar_type, p, i * 86_400_000_000_000) for i, p in enumerate(prices)]

    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ParquetDataCatalog(tmp_dir)
        catalog.write_data([instrument])
        catalog.write_data(bars)

        spawn_rules_json = [
            {
                "condition": {
                    "combinator": "AND",
                    "conditions": [
                        {
                            "left": {
                                "indicator": "MA",
                                "bar_type": bar_type_str,
                                "params": {"period": 2, "ma_type": "SIMPLE"},
                            },
                            "op": ">",
                            "right": {"value": 80},
                        }
                    ],
                },
                "strategy": {
                    "class": "backtest_runner.ema_cross_flat:EMACrossFlat",
                    "params": {
                        "instrument_id": str(instrument.id),
                        "bar_type": bar_type_str,
                        "trade_size": 10,
                        "fast_ema_period": 1,
                        "slow_ema_period": 2,
                        "request_bars": False,
                        "subscribe_trade_ticks": False,
                    },
                },
            }
        ]

        report = run_backtest(
            instrument_id=str(instrument.id),
            bar_type_str=bar_type_str,
            start_ns=bars[0].ts_event,
            end_ns=bars[-1].ts_event,
            catalog_path=tmp_dir,
            spawn_rules_json=spawn_rules_json,
        )

    assert report["instrument_id"] == str(instrument.id)
    assert report["bar_count"] == len(bars)
    assert "sharpe_ratio" in report
    assert "max_drawdown" in report
    assert "total_pnl" in report
    assert "total_pnl_pct" in report


def test_run_backtest_raises_value_error_when_no_bars_in_range():
    instrument = build_us_equity("AAPL")
    bar_type = bar_type_for(instrument.id)
    bar_type_str = str(bar_type)
    bars = [_bar(bar_type, 100, i * 86_400_000_000_000) for i in range(3)]

    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ParquetDataCatalog(tmp_dir)
        catalog.write_data([instrument])
        catalog.write_data(bars)

        with pytest.raises(ValueError, match="AAPL"):
            run_backtest(
                instrument_id=str(instrument.id),
                bar_type_str=bar_type_str,
                start_ns=10_000_000_000_000,
                end_ns=20_000_000_000_000,
                catalog_path=tmp_dir,
                spawn_rules_json=[],
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backtest_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest_runner.runner'`

- [ ] **Step 3: Implement `backtest_runner/runner.py`**

```python
# backtest_runner/runner.py
from nautilus_trader.analysis import MaxDrawdown
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FillModel, FixedFeeModel
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from backtest_runner.gated_strategy import make_gated_strategy_class
from strategy_spawner.spawner_parser import SpawnerParser


def run_backtest(
    instrument_id: str,
    bar_type_str: str,
    start_ns: int,
    end_ns: int,
    catalog_path: str,
    spawn_rules_json: list[dict],
    starting_balance: float = 100_000,
) -> dict:
    catalog = ParquetDataCatalog(catalog_path)

    instruments = catalog.instruments(instrument_ids=[instrument_id])
    if not instruments:
        raise ValueError(f"no instrument found in catalog for {instrument_id!r}")
    instrument = instruments[0]

    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise ValueError(
            f"no bars found for {instrument_id!r} {bar_type_str!r} "
            f"in range [{start_ns}, {end_ns}]"
        )

    currency = instrument.quote_currency

    engine = BacktestEngine()
    engine.add_venue(
        venue=instrument.id.venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(starting_balance, currency)],
        base_currency=currency,
        fee_model=FixedFeeModel(Money(1, currency)),
        fill_model=FillModel(prob_slippage=0.1),
    )
    engine.portfolio.analyzer.register_statistic(MaxDrawdown())
    engine.add_instrument(instrument)
    engine.add_data(bars)

    rules = SpawnerParser.parse(spawn_rules_json)
    for rule in rules:
        gated_cls = make_gated_strategy_class(rule.strategy_class, rule.condition_set)
        engine.add_strategy(gated_cls(**rule.params))

    engine.run()

    positions = engine.cache.positions()
    account = engine.cache.account_for_venue(instrument.id.venue)
    engine.portfolio.analyzer.calculate_statistics(account, positions)

    stats_returns = engine.portfolio.analyzer.get_performance_stats_returns()
    stats_pnls = engine.portfolio.analyzer.get_performance_stats_pnls(currency)

    return {
        "instrument_id": instrument_id,
        "bar_count": len(bars),
        "sharpe_ratio": stats_returns.get("Sharpe Ratio (252 days)"),
        "max_drawdown": stats_returns.get("Max Drawdown"),
        "total_pnl": stats_pnls.get("PnL (total)"),
        "total_pnl_pct": stats_pnls.get("PnL% (total)"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backtest_runner.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + this plan's 6 new tests across
all 3 tasks: 2 in `test_ema_cross_flat.py`, 2 in `test_gated_strategy.py`,
2 in `test_backtest_runner.py`)

- [ ] **Step 6: Commit**

```bash
git add backtest_runner/runner.py tests/test_backtest_runner.py
git commit -m "feat: add run_backtest entry point for automated backtest + reporting"
```

---

### Task 4: Update progress ledger, dispatch final review, manual verification

**Files:** none (bookkeeping only)

- [ ] **Step 1: Append to the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 9: backtest automation (spec 1df44b0, plan <this commit>) ---
Task 1: complete (backtest_runner/ema_cross_flat.py, commit <hash>)
Task 2: complete (backtest_runner/gated_strategy.py, commit <hash>)
Task 3: complete (backtest_runner/runner.py, commit <hash>)
```

- [ ] **Step 2: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
right before Task 1 (the spec commit, `1df44b0`) as the base. Run
`scripts/review-package 1df44b0 HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 9 complete.

- [ ] **Step 3: Manual end-to-end verification against real AAPL data (not automated)**

```python
from backtest_runner.runner import run_backtest

report = run_backtest(
    instrument_id="AAPL.NASDAQ",
    bar_type_str="AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
    start_ns=0,
    end_ns=9_999_999_999_999_999_999,
    catalog_path="./catalog",
    spawn_rules_json=[
        {
            "condition": {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {
                            "indicator": "RSI",
                            "bar_type": "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
                            "params": {"period": 14},
                        },
                        "op": "<",
                        "right": {"value": 70},
                    }
                ],
            },
            "strategy": {
                "class": "backtest_runner.ema_cross_flat:EMACrossFlat",
                "params": {
                    "instrument_id": "AAPL.NASDAQ",
                    "bar_type": "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
                    "trade_size": 10,
                    "fast_ema_period": 10,
                    "slow_ema_period": 20,
                },
            },
        }
    ],
)
print(report)
```

Confirm `report["bar_count"] == 250` (sub-8's ingested AAPL bar count) and
`sharpe_ratio`/`max_drawdown`/`total_pnl`/`total_pnl_pct` are all real
numbers (not `None`, and not the everything-`nan` zero-trade pattern,
unless the RSI condition genuinely never triggers across this data — if so,
note that finding rather than treating it as a bug). If any value looks
wrong, do not guess at a fix — escalate to the user per the spec's "Open
Questions" framing.

## Out of scope (reminder, per spec)

Do not add: multiple instruments/venues per run, live `TradingNode`
execution, new trading-strategy logic beyond the `EMACross` wrapper,
realistic IB-specific commission/slippage modeling, or changes to
`condition_engine`/`strategy_spawner.spawner_parser`. These belong to a
later sub-project if ever needed.
