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
