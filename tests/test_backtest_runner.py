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
