import datetime as dt
import json
import os
import random
import statistics as _stats
import threading
import uuid
from pathlib import Path
from typing import Literal

import requests

import numpy as np

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pydantic import BaseModel

from adapters.data_provider import bar_type_for
from ai_strategy.advisor import recommend_strategy
from backtest_runner.runner import run_backtest
from backtest_runner.simple_runner import run_simple_backtest
from beta_analysis.beta import beta_for_pair
from correlation_analysis.correlation import corr_matrix
from correlation_analysis.returns import compute_returns
from risk_analysis.metrics import compute_risk_metrics
from risk_analysis.rolling import rolling_beta as compute_rolling_beta
from risk_analysis.portfolio import markowitz_optimize
from risk_analysis.timeseries import compute_timeseries
from live_engine.engine import engine as live_engine, make_broker
from live_engine.broker_interface import BotStatus
from fred.client import FREDClient, SERIES_CATALOG as FRED_CATALOG
from ecos.client import ECOSClient, SERIES_CATALOG as ECOS_CATALOG
from corp_finance.client import CorpFinanceClient, STOCK_CRNO_MAP, parse_financials
from monte_carlo.simulator import run_monte_carlo
from regime_filter.detector import detect_regime
from krx.client import KRXClient
from sec_edgar.client import SECEdgarClient
from ksd.client import KSDClient, isin_from_code
from options.pricer import bs_price, bs_greeks, implied_vol, bs_chain, bs_iv_surface
from futures.pricer import futures_price, futures_calendar, futures_roll
from forex.pricer import fx_forward, fx_curve, fx_carry
from hyperliquid.client import get_meta_and_ctxs, get_candles, get_l2_book
from backends.ib.client import IBClient
from backends.kis.client import KISClient
from backends.kis.order_client import KISOrderClient
from backends.ib.order_client import IBOrderClient
from kr_universe.client import search_universe, get_universe as _get_kr_universe
from condition_engine.parser import ConditionParser
from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry, _BUILDERS as _INDICATOR_BUILDERS

CATALOG_PATH = "./catalog"
BOTS_FILE = Path("./bots.json")

app = FastAPI(title="Seokminal Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


def date_to_ns(date_str: str) -> int:
    parsed = dt.date.fromisoformat(date_str)
    event_date = dt.datetime.combine(parsed, dt.time.min, tzinfo=dt.timezone.utc)
    return int(event_date.timestamp() * 1_000_000_000)


def ns_to_date(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc).strftime("%Y-%m-%d")


class BarOut(BaseModel):
    ts_event: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsResponse(BaseModel):
    instrument_id: str
    bars: list[BarOut]


@app.get("/bars", response_model=BarsResponse)
def get_bars(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> BarsResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    all_bars = catalog.bars(bar_types=[bar_type_str])

    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {instrument_id!r} in range [{start}, {end}]",
        )

    return BarsResponse(
        instrument_id=instrument_id,
        bars=[
            BarOut(
                ts_event=b.ts_event,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in bars
        ],
    )


class TradeRecord(BaseModel):
    entry_ts_ns: int
    exit_ts_ns: int | None
    entry_price: float
    exit_price: float | None
    side: str
    pnl: float | None
    qty: float


class BacktestResponse(BaseModel):
    sharpe_ratio: float | None
    sortino_ratio: float | None = None
    max_drawdown: float | None
    volatility: float | None = None
    beta: float | None = None
    total_pnl: float | None
    total_pnl_pct: float | None
    win_rate: float | None = None
    profit_loss_ratio: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    bar_count: int
    trades: list[TradeRecord] = []


SUPPORTED_STRATEGIES = {"ema_cross", "gated", "macd", "rsi", "xgb"}


class BestParamsResponse(BaseModel):
    best_params: dict
    best_sharpe: float | None
    combinations_tested: int


@app.get("/backtest/optimize", response_model=BestParamsResponse)
def optimize_backtest(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    strategy: str = Query(..., description="'macd' or 'rsi'"),
) -> BestParamsResponse:
    if strategy not in {"macd", "rsi"}:
        raise HTTPException(status_code=400, detail="optimize only supports 'macd' or 'rsi'")

    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    catalog = ParquetDataCatalog(CATALOG_PATH)
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise HTTPException(status_code=400, detail=f"no bars found for {instrument_id!r}")

    if strategy == "macd":
        grid = [
            {"fast": f, "slow": s, "signal_period": sig, "trade_size": 10}
            for f in [8, 10, 12]
            for s in [20, 24, 26]
            for sig in [7, 9, 11]
            if f < s
        ]
    else:  # rsi
        grid = [
            {"period": p, "oversold": float(os), "overbought": float(ob), "trade_size": 10}
            for p in [10, 14, 18]
            for os in [25, 30, 35]
            for ob in [65, 70, 75]
        ]

    best_sharpe: float | None = None
    best_params: dict = grid[0]

    for params in grid:
        try:
            report = run_simple_backtest(bars, strategy, params)
            sh = report.get("sharpe_ratio")
            if sh is not None and (best_sharpe is None or sh > best_sharpe):
                best_sharpe = sh
                best_params = dict(params)
        except Exception:
            continue

    return BestParamsResponse(
        best_params=best_params,
        best_sharpe=best_sharpe,
        combinations_tested=len(grid),
    )


PORTFOLIO_STRATEGIES = {"ema_cross", "macd", "rsi"}


class PortfolioInstrumentResult(BaseModel):
    instrument_id: str
    sharpe_ratio: float | None
    total_pnl: float | None
    total_pnl_pct: float | None
    max_drawdown: float | None
    win_rate: float | None
    trade_count: int
    bar_count: int


class EquityPoint(BaseModel):
    ts_ns: int
    equity: float


class WalkForwardWindow(BaseModel):
    window_start: str
    window_end: str
    sharpe_ratio: float | None
    total_pnl_pct: float | None
    win_rate: float | None
    max_drawdown: float | None
    num_trades: int


class WalkForwardSummary(BaseModel):
    avg_sharpe: float | None
    avg_pnl_pct: float | None
    profitable_windows: int
    total_windows: int
    avg_max_drawdown: float | None


class WalkForwardResponse(BaseModel):
    instrument_id: str
    strategy: str
    n_windows: int
    windows: list[WalkForwardWindow]
    summary: WalkForwardSummary


class PortfolioBacktestResponse(BaseModel):
    results: list[PortfolioInstrumentResult]
    portfolio_equity: list[EquityPoint]
    portfolio_total_pnl: float | None
    portfolio_max_drawdown: float | None
    portfolio_sharpe: float | None = None


@app.get("/backtest/portfolio", response_model=PortfolioBacktestResponse)
def get_portfolio_backtest(
    instrument_ids: str = Query(..., description="Comma-separated instrument IDs"),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    strategy: str = Query(...),
    fast: int = Query(12),
    slow: int = Query(26),
    signal_period: int = Query(9),
    period: int = Query(14),
    oversold: float = Query(30.0),
    overbought: float = Query(70.0),
    trade_size: int = Query(10),
) -> PortfolioBacktestResponse:
    ids = [i.strip() for i in instrument_ids.split(",") if i.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="instrument_ids must not be empty")
    if strategy not in PORTFOLIO_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"portfolio-backtest only supports {sorted(PORTFOLIO_STRATEGIES)}",
        )

    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())

    if strategy == "macd":
        params = {"fast": fast, "slow": slow, "signal_period": signal_period, "trade_size": trade_size}
    elif strategy == "rsi":
        params = {"period": period, "oversold": oversold, "overbought": overbought, "trade_size": trade_size}
    else:  # ema_cross
        params = {"fast": fast, "slow": slow, "trade_size": trade_size}

    catalog = ParquetDataCatalog(CATALOG_PATH)
    results: list[PortfolioInstrumentResult] = []
    all_trades: list[dict] = []

    for iid in ids:
        try:
            bar_type_str = str(bar_type_for(InstrumentId.from_str(iid)))
        except Exception:
            continue
        all_iid_bars = catalog.bars(bar_types=[bar_type_str])
        bars = [b for b in all_iid_bars if start_ns <= b.ts_event <= end_ns]
        if not bars:
            continue
        try:
            report = run_simple_backtest(bars, strategy, params)
        except Exception:
            continue
        results.append(PortfolioInstrumentResult(
            instrument_id=iid,
            sharpe_ratio=report.get("sharpe_ratio"),
            total_pnl=report.get("total_pnl"),
            total_pnl_pct=report.get("total_pnl_pct"),
            max_drawdown=report.get("max_drawdown"),
            win_rate=report.get("win_rate"),
            trade_count=len(report.get("trades", [])),
            bar_count=report["bar_count"],
        ))
        for t in report.get("trades", []):
            if t.get("exit_ts_ns") is not None and t.get("pnl") is not None:
                all_trades.append({"ts_ns": t["exit_ts_ns"], "pnl": t["pnl"]})

    # Build portfolio equity curve sorted by trade exit timestamp
    all_trades.sort(key=lambda t: t["ts_ns"])
    equity = 0.0
    equity_series: list[EquityPoint] = [EquityPoint(ts_ns=start_ns, equity=0.0)]
    for t in all_trades:
        equity += t["pnl"]
        equity_series.append(EquityPoint(ts_ns=t["ts_ns"], equity=equity))

    # Portfolio-level stats
    pnls = [r.total_pnl for r in results if r.total_pnl is not None]
    portfolio_total_pnl: float | None = sum(pnls) if pnls else None

    portfolio_max_drawdown: float | None = None
    if len(equity_series) >= 2:
        peak = equity_series[0].equity
        worst = 0.0
        for ep in equity_series:
            if ep.equity > peak:
                peak = ep.equity
            dd = (ep.equity - peak) / peak if peak > 0 else 0.0
            if dd < worst:
                worst = dd
        portfolio_max_drawdown = worst if worst != 0.0 else None

    return PortfolioBacktestResponse(
        results=results,
        portfolio_equity=equity_series,
        portfolio_total_pnl=portfolio_total_pnl,
        portfolio_max_drawdown=portfolio_max_drawdown,
        portfolio_sharpe=None,
    )


_SIMPLE_STRATEGIES = {"macd", "rsi", "xgb", "ema_cross"}


@app.get("/backtest/walk-forward", response_model=WalkForwardResponse)
def get_walk_forward(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    strategy: str = Query(...),
    n_windows: int = Query(5, ge=2, le=20),
    trade_size: int = Query(10),
    # EMA Cross / shared
    fast: int = Query(12),
    slow: int = Query(26),
    # MACD
    signal_period: int = Query(9),
    # RSI
    period: int = Query(14),
    oversold: float = Query(30.0),
    overbought: float = Query(70.0),
    # XGBoost
    xgb_train_ratio: float = Query(0.7),
    xgb_n_estimators: int = Query(100),
    xgb_max_depth: int = Query(4),
    xgb_learning_rate: float = Query(0.1),
) -> WalkForwardResponse:
    if strategy not in _SIMPLE_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"walk-forward supports {_SIMPLE_STRATEGIES}, got {strategy!r}",
        )

    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    catalog = ParquetDataCatalog(CATALOG_PATH)
    all_bars_raw = catalog.bars(bar_types=[bar_type_str])
    all_bars = sorted(
        [b for b in all_bars_raw if start_ns <= b.ts_event <= end_ns],
        key=lambda b: b.ts_event,
    )
    if len(all_bars) < n_windows * 5:
        raise HTTPException(
            status_code=400,
            detail=f"need at least {n_windows * 5} bars, got {len(all_bars)}",
        )

    if strategy == "ema_cross":
        params = {"fast": fast, "slow": slow, "trade_size": trade_size}
    elif strategy == "macd":
        params = {"fast": fast, "slow": slow, "signal_period": signal_period, "trade_size": trade_size}
    elif strategy == "rsi":
        params = {"period": period, "oversold": oversold, "overbought": overbought, "trade_size": trade_size}
    else:  # xgb
        params = {
            "train_ratio": xgb_train_ratio,
            "n_estimators": xgb_n_estimators,
            "max_depth": xgb_max_depth,
            "learning_rate": xgb_learning_rate,
            "trade_size": trade_size,
        }

    window_size = len(all_bars) // n_windows
    windows: list[WalkForwardWindow] = []

    for i in range(n_windows):
        start_idx = i * window_size
        end_idx = start_idx + window_size if i < n_windows - 1 else len(all_bars)
        w_bars = all_bars[start_idx:end_idx]
        if len(w_bars) < 5:
            continue
        w_start = ns_to_date(w_bars[0].ts_event)
        w_end = ns_to_date(w_bars[-1].ts_event)
        try:
            report = run_simple_backtest(w_bars, strategy, params)
            windows.append(WalkForwardWindow(
                window_start=w_start,
                window_end=w_end,
                sharpe_ratio=report.get("sharpe_ratio"),
                total_pnl_pct=report.get("total_pnl_pct"),
                win_rate=report.get("win_rate"),
                max_drawdown=report.get("max_drawdown"),
                num_trades=report.get("num_trades", 0),
            ))
        except Exception:
            windows.append(WalkForwardWindow(
                window_start=w_start,
                window_end=w_end,
                sharpe_ratio=None,
                total_pnl_pct=None,
                win_rate=None,
                max_drawdown=None,
                num_trades=0,
            ))

    sharpes = [w.sharpe_ratio for w in windows if w.sharpe_ratio is not None]
    pnls = [w.total_pnl_pct for w in windows if w.total_pnl_pct is not None]
    dds = [w.max_drawdown for w in windows if w.max_drawdown is not None]

    summary = WalkForwardSummary(
        avg_sharpe=_stats.mean(sharpes) if sharpes else None,
        avg_pnl_pct=_stats.mean(pnls) if pnls else None,
        profitable_windows=sum(1 for p in pnls if p > 0),
        total_windows=len(windows),
        avg_max_drawdown=_stats.mean(dds) if dds else None,
    )

    return WalkForwardResponse(
        instrument_id=instrument_id,
        strategy=strategy,
        n_windows=n_windows,
        windows=windows,
        summary=summary,
    )


@app.get("/backtest", response_model=BacktestResponse)
def get_backtest(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    strategy: str = Query(...),
    fast: int = Query(12),
    slow: int = Query(26),
    trade_size: int = Query(10),
    benchmark_id: str | None = Query(None, description="베타 계산용 벤치마크 (e.g. 005930.XKRX, SPY.ARCA)"),
    spawn_rules: str | None = Query(None, description="복합 전략용 spawn_rules JSON (strategy=gated 일 때 필수)"),
    # MACD params
    signal_period: int = Query(9, description="MACD signal EMA period"),
    # RSI params
    period: int = Query(14, description="RSI period"),
    oversold: float = Query(30.0, description="RSI oversold threshold"),
    overbought: float = Query(70.0, description="RSI overbought threshold"),
    # XGBoost params
    xgb_train_ratio: float = Query(0.7, description="XGBoost train/test split ratio"),
    xgb_n_estimators: int = Query(100, description="XGBoost number of trees"),
    xgb_max_depth: int = Query(4, description="XGBoost tree max depth"),
    xgb_learning_rate: float = Query(0.1, description="XGBoost learning rate"),
) -> BacktestResponse:
    if strategy not in SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported strategy {strategy!r}, expected one of {SUPPORTED_STRATEGIES}",
        )

    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    # Route MACD, RSI, and XGBoost to the pure-Python simple runner
    if strategy in {"macd", "rsi", "xgb"}:
        catalog = ParquetDataCatalog(CATALOG_PATH)
        all_bars = catalog.bars(bar_types=[bar_type_str])
        simple_bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
        if not simple_bars:
            raise HTTPException(status_code=400, detail=f"no bars found for {instrument_id!r}")
        if strategy == "macd":
            simple_params = {"fast": fast, "slow": slow, "signal_period": signal_period, "trade_size": trade_size}
        elif strategy == "rsi":
            simple_params = {"period": period, "oversold": oversold, "overbought": overbought, "trade_size": trade_size}
        else:  # xgb
            simple_params = {
                "train_ratio": xgb_train_ratio,
                "n_estimators": xgb_n_estimators,
                "max_depth": xgb_max_depth,
                "learning_rate": xgb_learning_rate,
                "trade_size": trade_size,
            }
        try:
            report = run_simple_backtest(simple_bars, strategy, simple_params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return BacktestResponse(
            sharpe_ratio=report["sharpe_ratio"],
            sortino_ratio=report.get("sortino_ratio"),
            max_drawdown=report.get("max_drawdown"),
            volatility=report.get("volatility"),
            beta=None,
            total_pnl=report.get("total_pnl"),
            total_pnl_pct=report.get("total_pnl_pct"),
            win_rate=report.get("win_rate"),
            profit_loss_ratio=report.get("profit_loss_ratio"),
            avg_win=report.get("avg_win"),
            avg_loss=report.get("avg_loss"),
            bar_count=report["bar_count"],
            trades=[TradeRecord(**t) for t in report.get("trades", [])],
        )

    if strategy == "gated":
        if not spawn_rules:
            raise HTTPException(status_code=400, detail="spawn_rules required for gated strategy")
        try:
            spawn_rules_json = json.loads(spawn_rules)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"invalid spawn_rules JSON: {exc}") from exc
    else:  # ema_cross
        spawn_rules_json = [
            {
                "condition": {"combinator": "AND", "conditions": []},
                "strategy": {
                    "class": "backtest_runner.ema_cross_flat:EMACrossFlat",
                    "params": {
                        "instrument_id": instrument_id,
                        "bar_type": bar_type_str,
                        "trade_size": trade_size,
                        "fast_ema_period": fast,
                        "slow_ema_period": slow,
                        "request_bars": False,
                        "subscribe_trade_ticks": False,
                    },
                },
            }
        ]

    try:
        report = run_backtest(
            instrument_id=instrument_id,
            bar_type_str=bar_type_str,
            start_ns=start_ns,
            end_ns=end_ns,
            catalog_path=CATALOG_PATH,
            spawn_rules_json=spawn_rules_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    beta_val: float | None = None
    if benchmark_id:
        try:
            start_ns = date_to_ns(start.isoformat())
            end_ns = date_to_ns(end.isoformat())
            bench_bar_str = str(bar_type_for(InstrumentId.from_str(benchmark_id)))
            beta_result = beta_for_pair(
                inst_id=instrument_id,
                inst_bar_type=bar_type_str,
                bench_id=benchmark_id,
                bench_bar_type=bench_bar_str,
                start_ns=start_ns,
                end_ns=end_ns,
                catalog_path=CATALOG_PATH,
            )
            beta_val = beta_result["beta"]
        except Exception:
            pass

    return BacktestResponse(
        sharpe_ratio=report["sharpe_ratio"],
        sortino_ratio=report.get("sortino_ratio"),
        max_drawdown=report["max_drawdown"],
        volatility=report.get("volatility"),
        beta=beta_val,
        total_pnl=report["total_pnl"],
        total_pnl_pct=report["total_pnl_pct"],
        win_rate=report.get("win_rate"),
        profit_loss_ratio=report.get("profit_loss_ratio"),
        avg_win=report.get("avg_win"),
        avg_loss=report.get("avg_loss"),
        bar_count=report["bar_count"],
        trades=[TradeRecord(**t) for t in report.get("trades", [])],
    )


class BetaResponse(BaseModel):
    instrument_id: str
    benchmark_id: str
    beta: float
    correlation: float


class CorrelationPair(BaseModel):
    a: str
    b: str
    correlation: float


class CorrelationResponse(BaseModel):
    pairs: list[CorrelationPair]


@app.get("/correlation", response_model=CorrelationResponse)
def get_correlation(
    instrument_ids: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> CorrelationResponse:
    ids = instrument_ids.split(",")
    bar_type_strs = [
        str(bar_type_for(InstrumentId.from_str(instrument_id))) for instrument_id in ids
    ]
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())

    try:
        matrix = corr_matrix(
            instrument_ids=ids,
            bar_type_strs=bar_type_strs,
            start_ns=start_ns,
            end_ns=end_ns,
            catalog_path=CATALOG_PATH,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    seen: set[tuple[str, str]] = set()
    pairs = []
    for (a, b), correlation in matrix.items():
        # Skip self-correlation pairs
        if a == b:
            continue
        # Check both orderings to avoid duplicates
        canonical_key = tuple(sorted((a, b)))
        if canonical_key in seen:
            continue
        seen.add(canonical_key)
        # Output using the original order from the matrix
        pairs.append(CorrelationPair(a=a, b=b, correlation=correlation))

    return CorrelationResponse(pairs=pairs)


@app.get("/beta", response_model=BetaResponse)
def get_beta(
    instrument_id: str = Query(...),
    benchmark_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> BetaResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())

    try:
        result = beta_for_pair(
            instrument_id=instrument_id,
            benchmark_id=benchmark_id,
            start_ns=start_ns,
            end_ns=end_ns,
            catalog_path=CATALOG_PATH,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BetaResponse(
        instrument_id=result["instrument_id"],
        benchmark_id=result["benchmark_id"],
        beta=result["beta"],
        correlation=result["correlation"],
    )


# ── /risk ──────────────────────────────────────────────────────────────────────

class RiskMetricsResponse(BaseModel):
    instrument_id: str
    sharpe_ratio: float | None
    sortino_ratio: float | None
    volatility: float | None
    max_drawdown: float | None
    var_95: float | None
    calmar_ratio: float | None
    alpha: float | None
    r_squared: float | None
    annualized_return: float | None
    observation_count: int


@app.get("/risk", response_model=RiskMetricsResponse)
def get_risk(
    instrument_id: str = Query(...),
    benchmark_id: str | None = Query(None),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> RiskMetricsResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    catalog = ParquetDataCatalog(CATALOG_PATH)

    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise HTTPException(status_code=400, detail=f"no bars found for {instrument_id!r}")

    inst_returns_map = compute_returns(bars)
    inst_returns = [inst_returns_map[ts] for ts in sorted(inst_returns_map)]

    bench_returns_aligned: list[float] | None = None
    if benchmark_id:
        bench_bar_type_str = str(bar_type_for(InstrumentId.from_str(benchmark_id)))
        bench_all = catalog.bars(bar_types=[bench_bar_type_str])
        bench_bars = [b for b in bench_all if start_ns <= b.ts_event <= end_ns]
        if bench_bars:
            bench_map = compute_returns(bench_bars)
            common = sorted(set(inst_returns_map) & set(bench_map))
            if len(common) >= 2:
                inst_returns = [inst_returns_map[d] for d in common]
                bench_returns_aligned = [bench_map[d] for d in common]

    try:
        metrics = compute_risk_metrics(inst_returns, bench_returns_aligned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RiskMetricsResponse(instrument_id=instrument_id, **metrics)


# ── /rolling-beta ──────────────────────────────────────────────────────────────

class RollingBetaPoint(BaseModel):
    ts_ns: int
    beta: float
    correlation: float


class RollingBetaResponse(BaseModel):
    instrument_id: str
    benchmark_id: str
    window: int
    points: list[RollingBetaPoint]


@app.get("/rolling-beta", response_model=RollingBetaResponse)
def get_rolling_beta(
    instrument_id: str = Query(...),
    benchmark_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    window: int = Query(30),
) -> RollingBetaResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    catalog = ParquetDataCatalog(CATALOG_PATH)

    def _get_returns(iid: str) -> dict[int, float]:
        bt = str(bar_type_for(InstrumentId.from_str(iid)))
        bars = [b for b in catalog.bars(bar_types=[bt]) if start_ns <= b.ts_event <= end_ns]
        if not bars:
            raise HTTPException(status_code=400, detail=f"no bars found for {iid!r}")
        return compute_returns(bars)

    try:
        inst_map = _get_returns(instrument_id)
        bench_map = _get_returns(benchmark_id)
        points = compute_rolling_beta(inst_map, bench_map, window=window)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RollingBetaResponse(
        instrument_id=instrument_id,
        benchmark_id=benchmark_id,
        window=window,
        points=[RollingBetaPoint(**p) for p in points],
    )


# ── /timeseries ────────────────────────────────────────────────────────────────

class TimeSeriesPoint(BaseModel):
    ts_ns: int
    daily_return: float
    cumulative_return: float
    drawdown: float
    rolling_sharpe: float | None
    benchmark_cumulative: float | None


class TimeSeriesResponse(BaseModel):
    instrument_id: str
    points: list[TimeSeriesPoint]


@app.get("/timeseries", response_model=TimeSeriesResponse)
def get_timeseries(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    benchmark_id: str | None = Query(None),
    rolling_window: int = Query(60),
) -> TimeSeriesResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    catalog = ParquetDataCatalog(CATALOG_PATH)

    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise HTTPException(status_code=400, detail=f"no bars for {instrument_id!r}")

    inst_map = compute_returns(bars)

    bench_map = None
    if benchmark_id:
        bench_bt = str(bar_type_for(InstrumentId.from_str(benchmark_id)))
        bench_bars = [b for b in catalog.bars(bar_types=[bench_bt]) if start_ns <= b.ts_event <= end_ns]
        if bench_bars:
            bench_map = compute_returns(bench_bars)

    points = compute_timeseries(inst_map, bench_map, rolling_window=rolling_window)
    return TimeSeriesResponse(
        instrument_id=instrument_id,
        points=[TimeSeriesPoint(**p) for p in points],
    )


# ── /portfolio/optimize ────────────────────────────────────────────────────────

class PortfolioWeights(BaseModel):
    weights: dict[str, float]
    expected_return: float
    volatility: float
    sharpe: float | None = None


class FrontierPoint(BaseModel):
    expected_return: float
    volatility: float


class PortfolioOptimizeResponse(BaseModel):
    instruments: list[str]
    min_variance: PortfolioWeights
    max_sharpe: PortfolioWeights
    efficient_frontier: list[FrontierPoint]


@app.get("/portfolio/optimize", response_model=PortfolioOptimizeResponse)
def get_portfolio_optimize(
    instrument_ids: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> PortfolioOptimizeResponse:
    ids = [i.strip() for i in instrument_ids.split(",")]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 instrument_ids")

    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    catalog = ParquetDataCatalog(CATALOG_PATH)

    returns_maps: dict[str, dict[int, float]] = {}
    for iid in ids:
        bt = str(bar_type_for(InstrumentId.from_str(iid)))
        bars = [b for b in catalog.bars(bar_types=[bt]) if start_ns <= b.ts_event <= end_ns]
        if not bars:
            raise HTTPException(status_code=400, detail=f"no bars found for {iid!r}")
        returns_maps[iid] = compute_returns(bars)

    common_dates = sorted(
        set.intersection(*[set(m.keys()) for m in returns_maps.values()])
    )
    if len(common_dates) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"need at least 30 common dates, got {len(common_dates)}"
        )

    aligned: dict[str, list[float]] = {
        iid: [returns_maps[iid][d] for d in common_dates] for iid in ids
    }

    try:
        result = markowitz_optimize(aligned)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PortfolioOptimizeResponse(
        instruments=result["instruments"],
        min_variance=PortfolioWeights(**result["min_variance"]),
        max_sharpe=PortfolioWeights(**result["max_sharpe"]),
        efficient_frontier=[FrontierPoint(**p) for p in result["efficient_frontier"]],
    )


# ── /bots ──────────────────────────────────────────────────────────────────────

class BotConfig(BaseModel):
    name: str
    strategy: str = "ema_cross"
    instrument_id: str
    fast_ema: int = 10
    slow_ema: int = 20
    trade_size: int = 10


class BotRecord(BaseModel):
    id: str
    name: str
    strategy: str
    instrument_id: str
    fast_ema: int
    slow_ema: int
    trade_size: int
    status: str  # "stopped" | "running" | "error"
    created_at: str


def _load_bots() -> dict[str, dict]:
    if BOTS_FILE.exists():
        return json.loads(BOTS_FILE.read_text())
    return {}


def _save_bots(b: dict[str, dict]) -> None:
    BOTS_FILE.write_text(json.dumps(b, indent=2))


# Module-level in-memory bot registry (loaded once at startup; tests manipulate directly)
bots: dict[str, dict] = _load_bots()


@app.get("/bots", response_model=list[BotRecord])
def list_bots() -> list[BotRecord]:
    bots = _load_bots()
    return [BotRecord(**v) for v in bots.values()]


@app.post("/bots", response_model=BotRecord, status_code=201)
def create_bot(config: BotConfig) -> BotRecord:
    global bots
    bots = _load_bots()
    bot_id = str(uuid.uuid4())[:8]
    record = {
        "id": bot_id,
        "name": config.name,
        "strategy": config.strategy,
        "instrument_id": config.instrument_id,
        "fast_ema": config.fast_ema,
        "slow_ema": config.slow_ema,
        "trade_size": config.trade_size,
        "status": "stopped",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    bots[bot_id] = record
    _save_bots(bots)
    return BotRecord(**record)


@app.post("/bots/{bot_id}/start", response_model=BotRecord)
async def start_bot(bot_id: str) -> BotRecord:
    global bots
    bots = _load_bots()
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")

    if not live_engine.is_running(bot_id):
        b = bots[bot_id]
        try:
            broker = make_broker(b["instrument_id"])
            await live_engine.start(
                bot_id=bot_id,
                instrument_id=b["instrument_id"],
                fast_ema=b["fast_ema"],
                slow_ema=b["slow_ema"],
                trade_size=b["trade_size"],
                broker=broker,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Missing env var {exc} — fill in .env file with broker credentials",
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    bots[bot_id]["status"] = "running"
    _save_bots(bots)
    return BotRecord(**bots[bot_id])


@app.post("/bots/{bot_id}/stop", response_model=BotRecord)
async def stop_bot(bot_id: str) -> BotRecord:
    global bots
    bots = _load_bots()
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")

    await live_engine.stop(bot_id)

    bots[bot_id]["status"] = "stopped"
    _save_bots(bots)
    return BotRecord(**bots[bot_id])


# ── Bot live status ────────────────────────────────────────────────────────────

class LiveBotStatusResponse(BaseModel):
    bot_id: str
    running: bool
    position: str
    qty: float
    last_price: float | None
    last_signal: str | None
    recent_orders: list[dict]
    error: str | None


# ── Bot trade/signal log models ────────────────────────────────────────────────

class ClosedTrade(BaseModel):
    entry_ts_ns: int | None
    exit_ts_ns: int
    side: str  # "LONG" | "SHORT"
    entry_price: float
    exit_price: float
    qty: int
    pnl: float


class SignalEntry(BaseModel):
    ts_ns: int
    signal: str
    price: float


class BotTradeLogResponse(BaseModel):
    bot_id: str
    trades: list[ClosedTrade]


class BotSignalLogResponse(BaseModel):
    bot_id: str
    signals: list[SignalEntry]


@app.get("/bots/{bot_id}/live-status", response_model=LiveBotStatusResponse)
def get_live_bot_status(bot_id: str) -> LiveBotStatusResponse:
    status = live_engine.get_status(bot_id)
    if status is None:
        bots = _load_bots()
        if bot_id not in bots:
            raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")
        return LiveBotStatusResponse(
            bot_id=bot_id, running=False, position="FLAT", qty=0,
            last_price=None, last_signal=None, recent_orders=[], error=None,
        )
    return LiveBotStatusResponse(
        bot_id=status.bot_id,
        running=status.running,
        position=status.position,
        qty=status.qty,
        last_price=status.last_price,
        last_signal=status.last_signal,
        recent_orders=[
            {"order_id": o.order_id, "status": o.status, "filled": o.filled}
            for o in status.orders
        ],
        error=status.error,
    )


# ── WebSocket: real-time price feed ───────────────────────────────────────────

@app.websocket("/ws/bots/{bot_id}/prices")
async def ws_bot_prices(websocket: WebSocket, bot_id: str) -> None:
    await websocket.accept()
    await live_engine.subscribe(bot_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive; data pushed by engine
    except WebSocketDisconnect:
        pass
    finally:
        await live_engine.unsubscribe(bot_id, websocket)


@app.delete("/bots/{bot_id}", status_code=204)
def delete_bot(bot_id: str) -> None:
    global bots
    bots = _load_bots()
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")
    del bots[bot_id]
    _save_bots(bots)


# ── /fred ──────────────────────────────────────────────────────────────────────

class FREDObservation(BaseModel):
    date: str
    value: float | None


class FREDSeriesResponse(BaseModel):
    series_id: str
    label: str
    unit: str
    category: str
    observations: list[FREDObservation]


class FREDCatalogItem(BaseModel):
    series_id: str
    label: str
    unit: str
    category: str


@app.get("/fred/catalog", response_model=list[FREDCatalogItem])
def get_fred_catalog() -> list[FREDCatalogItem]:
    return [
        FREDCatalogItem(series_id=sid, **meta)
        for sid, meta in FRED_CATALOG.items()
    ]


@app.get("/fred/series", response_model=FREDSeriesResponse)
def get_fred_series(
    series_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> FREDSeriesResponse:
    meta = FRED_CATALOG.get(series_id, {"label": series_id, "unit": "", "category": "custom"})
    try:
        client = FREDClient()
        observations = client.get_series(series_id, start.isoformat(), end.isoformat())
    except KeyError:
        raise HTTPException(status_code=500, detail="FRED_API_KEY not set in .env")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return FREDSeriesResponse(
        series_id=series_id,
        label=meta["label"],
        unit=meta["unit"],
        category=meta["category"],
        observations=[FREDObservation(**o) for o in observations],
    )


# ── /ecos ──────────────────────────────────────────────────────────────────────

class ECOSObservation(BaseModel):
    date: str
    value: float | None


class ECOSSeriesResponse(BaseModel):
    series_id: str
    label: str
    unit: str
    category: str
    observations: list[ECOSObservation]


class ECOSCatalogItem(BaseModel):
    series_id: str
    label: str
    unit: str
    category: str


@app.get("/ecos/catalog", response_model=list[ECOSCatalogItem])
def get_ecos_catalog() -> list[ECOSCatalogItem]:
    return [
        ECOSCatalogItem(series_id=sid, label=m["label"], unit=m["unit"], category=m["category"])
        for sid, m in ECOS_CATALOG.items()
    ]


@app.get("/ecos/series", response_model=ECOSSeriesResponse)
def get_ecos_series(
    series_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
) -> ECOSSeriesResponse:
    meta = ECOS_CATALOG.get(series_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Unknown ECOS series: {series_id!r}")
    try:
        client = ECOSClient()
        observations = client.get_series_by_id(series_id, start, end)
    except KeyError:
        raise HTTPException(status_code=500, detail="ECOS_API_KEY not set in .env")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ECOSSeriesResponse(
        series_id=series_id,
        label=meta["label"],
        unit=meta["unit"],
        category=meta["category"],
        observations=[ECOSObservation(**o) for o in observations],
    )


# ── /corp-finance ──────────────────────────────────────────────────────────────

class CorpFinancialYear(BaseModel):
    biz_year: str
    report_type: str
    currency: str
    sale_amt: int
    op_profit: int
    net_profit: int
    total_assets: int
    total_debt: int
    total_equity: int
    paid_in_capital: int
    op_margin_pct: float | None
    net_margin_pct: float | None
    roe_pct: float | None
    debt_ratio_pct: float


class CorpFinanceSummaryResponse(BaseModel):
    stock_code: str
    crno: str
    years: list[CorpFinancialYear]


class CorpCrnoItem(BaseModel):
    stock_code: str
    crno: str


@app.get("/corp-finance/crno-catalog", response_model=list[CorpCrnoItem])
def get_crno_catalog() -> list[CorpCrnoItem]:
    return [CorpCrnoItem(stock_code=k, crno=v) for k, v in STOCK_CRNO_MAP.items()]


@app.get("/corp-finance/summary", response_model=CorpFinanceSummaryResponse)
def get_corp_finance_summary(
    stock_code: str = Query(..., description="종목코드 (예: 005930)"),
    crno: str | None = Query(None, description="법인등록번호 (stock_code 맵에 없을 때 직접 입력)"),
    start_year: int = Query(2020),
    end_year: int = Query(2023),
    fncl_dcd: str = Query("110", description="110=연결, 120=별도"),
) -> CorpFinanceSummaryResponse:
    resolved_crno = crno or STOCK_CRNO_MAP.get(stock_code)
    if not resolved_crno:
        raise HTTPException(
            status_code=404,
            detail=f"crno not found for {stock_code!r}. Add via STOCK_CRNO_MAP or pass crno= param.",
        )
    try:
        client = CorpFinanceClient()
    except KeyError:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_API_KEY not set in .env")

    raw_items = client.get_multiyear(resolved_crno, start_year, end_year, fncl_dcd)
    if not raw_items:
        raise HTTPException(
            status_code=404,
            detail=f"No financial data for crno={resolved_crno} ({start_year}~{end_year})",
        )

    return CorpFinanceSummaryResponse(
        stock_code=stock_code,
        crno=resolved_crno,
        years=[CorpFinancialYear(**parse_financials(item)) for item in raw_items],
    )


# ── /monte-carlo ──────────────────────────────────────────────────────────────

class MCPaths(BaseModel):
    p5: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p95: list[float]


class MonteCarloResponse(BaseModel):
    instrument_id: str
    n_simulations: int
    horizon_days: int
    day_indices: list[int]
    paths: MCPaths
    terminal_mean: float
    terminal_median: float
    terminal_p5: float
    terminal_p95: float
    prob_profit: float
    prob_loss_20pct: float
    ann_return_mean: float
    ann_return_p5: float
    ann_return_p95: float
    max_dd_mean: float
    max_dd_p95: float


@app.get("/monte-carlo", response_model=MonteCarloResponse)
def get_monte_carlo(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    horizon_days: int = Query(252, ge=20, le=1260),
    n_simulations: int = Query(1000, ge=100, le=5000),
    benchmark_id: str | None = Query(None),
) -> MonteCarloResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = sorted([b for b in all_bars if start_ns <= b.ts_event <= end_ns], key=lambda b: b.ts_event)
    if len(bars) < 11:
        raise HTTPException(status_code=400, detail=f"need >=11 bars, got {len(bars)}")

    returns = []
    for i in range(1, len(bars)):
        prev = float(bars[i - 1].close)
        curr = float(bars[i].close)
        if prev > 0:
            returns.append((curr - prev) / prev)

    try:
        result = run_monte_carlo(returns, horizon_days=horizon_days, n_simulations=n_simulations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MonteCarloResponse(
        instrument_id=instrument_id,
        n_simulations=result["n_simulations"],
        horizon_days=result["horizon_days"],
        day_indices=result["day_indices"],
        paths=MCPaths(**result["paths"]),
        terminal_mean=result["terminal_mean"],
        terminal_median=result["terminal_median"],
        terminal_p5=result["terminal_p5"],
        terminal_p95=result["terminal_p95"],
        prob_profit=result["prob_profit"],
        prob_loss_20pct=result["prob_loss_20pct"],
        ann_return_mean=result["ann_return_mean"],
        ann_return_p5=result["ann_return_p5"],
        ann_return_p95=result["ann_return_p95"],
        max_dd_mean=result["max_dd_mean"],
        max_dd_p95=result["max_dd_p95"],
    )


# ── /regime ────────────────────────────────────────────────────────────────────

class RegimePoint(BaseModel):
    date_index: int
    vol: float
    sma: float
    price: float
    regime: str


class RegimeResponse(BaseModel):
    instrument_id: str
    current_regime: str
    current_vol: float | None
    current_sma: float | None
    vol_threshold: float
    sma_period: int
    vol_period: int
    regime_distribution: dict[str, float]
    regimes: list[RegimePoint]


@app.get("/regime", response_model=RegimeResponse)
def get_regime(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    sma_period: int = Query(50, ge=5, le=200),
    vol_period: int = Query(20, ge=5, le=60),
    vol_threshold: float | None = Query(None),
) -> RegimeResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())
    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = sorted([b for b in all_bars if start_ns <= b.ts_event <= end_ns], key=lambda b: b.ts_event)
    if len(bars) < sma_period + 2:
        raise HTTPException(status_code=400, detail=f"need >={sma_period + 2} bars, got {len(bars)}")

    closes = [float(b.close) for b in bars]
    try:
        result = detect_regime(closes, sma_period=sma_period, vol_period=vol_period, vol_threshold=vol_threshold)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RegimeResponse(
        instrument_id=instrument_id,
        current_regime=result["current_regime"],
        current_vol=result["current_vol"],
        current_sma=result["current_sma"],
        vol_threshold=result["vol_threshold"],
        sma_period=result["sma_period"],
        vol_period=result["vol_period"],
        regime_distribution=result["regime_distribution"],
        regimes=[RegimePoint(**r) for r in result["regimes"]],
    )


# ── /krx ───────────────────────────────────────────────────────────────────────

class KRXIndexRow(BaseModel):
    bas_dd: str
    idx_nm: str | None = None
    clpr: float | None = None
    vs: float | None = None
    flt_rt: float | None = None
    opn_prc: float | None = None
    hgpr: float | None = None
    lwpr: float | None = None
    acc_trdvol: float | None = None
    raw: dict


class KRXIndexResponse(BaseModel):
    bas_dd: str
    index_type: str
    rows: list[KRXIndexRow]


@app.get("/krx/index", response_model=KRXIndexResponse)
def get_krx_index(
    bas_dd: str = Query(..., description="기준일 YYYYMMDD"),
    index_type: str = Query("KOSPI", description="KRX | KOSPI | KOSDAQ"),
) -> KRXIndexResponse:
    import os
    key = os.environ.get("KRX_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="KRX_API_KEY not set in .env")
    try:
        client = KRXClient(api_key=key)
        rows_raw = client.get_index_daily(bas_dd, index_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = []
    for r in rows_raw:
        def _f(k: str) -> float | None:
            try: return float(str(r.get(k, "")).replace(",", ""))
            except (TypeError, ValueError): return None
        rows.append(KRXIndexRow(
            bas_dd=r.get("basDd", bas_dd),
            idx_nm=r.get("idxNm") or r.get("idx_nm"),
            clpr=_f("clpr") or _f("cls_prc"),
            vs=_f("vs"),
            flt_rt=_f("fltRt") or _f("flt_rt"),
            opn_prc=_f("opnPrc") or _f("opn_prc"),
            hgpr=_f("hgpr"),
            lwpr=_f("lwpr"),
            acc_trdvol=_f("accTrdvol") or _f("acc_trdvol"),
            raw=r,
        ))
    return KRXIndexResponse(bas_dd=bas_dd, index_type=index_type, rows=rows)


class KRXStockBaseRow(BaseModel):
    isu_cd: str | None = None
    isu_nm: str | None = None
    mkt_nm: str | None = None
    mktcap: float | None = None
    list_shrs: float | None = None
    raw: dict


class KRXStockBaseResponse(BaseModel):
    market: str
    rows: list[KRXStockBaseRow]


@app.get("/krx/stock-base", response_model=KRXStockBaseResponse)
def get_krx_stock_base(
    market: str = Query("KOSPI", description="KOSPI | KOSDAQ"),
) -> KRXStockBaseResponse:
    import os
    key = os.environ.get("KRX_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="KRX_API_KEY not set in .env")
    try:
        client = KRXClient(api_key=key)
        rows_raw = client.get_stock_base_info(market)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = []
    for r in rows_raw:
        def _f(k: str) -> float | None:
            try: return float(str(r.get(k, "")).replace(",", ""))
            except (TypeError, ValueError): return None
        rows.append(KRXStockBaseRow(
            isu_cd=r.get("isuCd") or r.get("isu_cd"),
            isu_nm=r.get("isuNm") or r.get("isu_nm"),
            mkt_nm=r.get("mktNm") or r.get("mkt_nm"),
            mktcap=_f("mktcap") or _f("mkt_cap"),
            list_shrs=_f("listShrs") or _f("list_shrs"),
            raw=r,
        ))
    return KRXStockBaseResponse(market=market, rows=rows)


# ── /edgar ─────────────────────────────────────────────────────────────────────

class EdgarAnnualRow(BaseModel):
    year: int
    revenue: float | None
    gross_profit: float | None
    op_income: float | None
    net_income: float | None
    total_assets: float | None
    equity: float | None
    long_term_debt: float | None
    eps_diluted: float | None
    op_margin_pct: float | None
    net_margin_pct: float | None
    roe_pct: float | None


class EdgarSummaryResponse(BaseModel):
    ticker: str
    cik: str
    rows: list[EdgarAnnualRow]


@app.get("/edgar/summary", response_model=EdgarSummaryResponse)
def get_edgar_summary(
    ticker: str = Query(..., description="US ticker (예: AAPL)"),
    start_year: int = Query(2019),
    end_year: int = Query(2024),
) -> EdgarSummaryResponse:
    try:
        client = SECEdgarClient()
        cik = client.get_cik(ticker.upper())
        rows_raw = client.get_annual_summary(ticker.upper(), start_year, end_year)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return EdgarSummaryResponse(
        ticker=ticker.upper(),
        cik=cik,
        rows=[EdgarAnnualRow(**r) for r in rows_raw],
    )


class EdgarConceptRow(BaseModel):
    end: str
    val: float
    form: str | None
    filed: str | None
    unit: str


class EdgarConceptResponse(BaseModel):
    ticker: str
    cik: str
    concept: str
    rows: list[EdgarConceptRow]


@app.get("/edgar/concept", response_model=EdgarConceptResponse)
def get_edgar_concept(
    ticker: str = Query(...),
    concept: str = Query(..., description="XBRL concept (예: Revenues, NetIncomeLoss)"),
    annual_only: bool = Query(True),
) -> EdgarConceptResponse:
    try:
        client = SECEdgarClient()
        cik = client.get_cik(ticker.upper())
        rows_raw = client.get_concept(cik, concept, annual_only=annual_only)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return EdgarConceptResponse(
        ticker=ticker.upper(),
        cik=cik,
        concept=concept,
        rows=[EdgarConceptRow(**r) for r in rows_raw],
    )


# ── /ksd ───────────────────────────────────────────────────────────────────────

def _ksd_client() -> KSDClient:
    try:
        return KSDClient()
    except KeyError as e:
        raise HTTPException(status_code=500, detail=str(e))


class KSDDividendRow(BaseModel):
    raw: dict
    isin_cd: str | None = None
    isin_cd_nm: str | None = None
    dvdn_bas_dt: str | None = None        # 배당기준일
    cash_dvdn_pay_dt: str | None = None   # 현금배당지급일
    stck_genr_dvdn_amt: str | None = None # 주당배당금
    stck_genr_cash_dvdn_rt: str | None = None  # 현금배당률
    stck_dvdn_rcd: str | None = None      # 배당사유코드
    stck_dvdn_rcd_nm: str | None = None   # 배당사유명
    scrs_itms_kcd_nm: str | None = None   # 주식종류(보통주/우선주)


class KSDDividendResponse(BaseModel):
    isin_cd: str
    rows: list[KSDDividendRow]


@app.get("/ksd/dividend", response_model=KSDDividendResponse)
def get_ksd_dividend(
    stock_code: str = Query(..., description="종목코드 (6자리) 또는 ISIN (12자리)"),
    begin_dt: str | None = Query(None, description="시작일 YYYYMMDD"),
    end_dt: str | None = Query(None, description="종료일 YYYYMMDD"),
) -> KSDDividendResponse:
    isin = isin_from_code(stock_code)
    try:
        rows_raw = _ksd_client().get_dividend(isin_cd=isin, begin_dt=begin_dt, end_dt=end_dt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _row(r: dict) -> KSDDividendRow:
        return KSDDividendRow(
            raw=r,
            isin_cd=r.get("isinCd"),
            isin_cd_nm=r.get("isinCdNm"),
            dvdn_bas_dt=r.get("dvdnBasDt"),
            cash_dvdn_pay_dt=r.get("cashDvdnPayDt"),
            stck_genr_dvdn_amt=r.get("stckGenrDvdnAmt"),
            stck_genr_cash_dvdn_rt=r.get("stckGenrCashDvdnRt"),
            stck_dvdn_rcd=r.get("stckDvdnRcd"),
            stck_dvdn_rcd_nm=r.get("stckDvdnRcdNm"),
            scrs_itms_kcd_nm=r.get("scrsItmsKcdNm"),
        )
    return KSDDividendResponse(isin_cd=isin, rows=[_row(r) for r in rows_raw])


class KSDBorrowRow(BaseModel):
    raw: dict
    rank: int | None = None
    isin_cd: str | None = None
    isin_cd_nm: str | None = None
    bas_dt: str | None = None
    lnb_ccl_stck_cnt: str | None = None   # 대차체결주식수
    lnb_rman_stck_cnt: str | None = None  # 대차잔여주식수
    lnb_bal: str | None = None            # 대차잔액


class KSDBorrowResponse(BaseModel):
    bas_dt: str
    rows: list[KSDBorrowRow]


@app.get("/ksd/borrow-rank", response_model=KSDBorrowResponse)
def get_ksd_borrow_rank(
    bas_dt: str = Query(..., description="기준일 YYYYMMDD"),
    top_n: int = Query(30, ge=1, le=100),
) -> KSDBorrowResponse:
    try:
        rows_raw = _ksd_client().get_borrowing_rank(bas_dt, top_n)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KSDBorrowResponse(
        bas_dt=bas_dt,
        rows=[KSDBorrowRow(
            raw=r, rank=i + 1,
            isin_cd=r.get("isinCd"), isin_cd_nm=r.get("isinCdNm"),
            bas_dt=r.get("basDt"),
            lnb_ccl_stck_cnt=r.get("lnbCclStckCnt"),
            lnb_rman_stck_cnt=r.get("lnbRmanStckCnt"),
            lnb_bal=r.get("lnbBal"),
        ) for i, r in enumerate(rows_raw)],
    )


class KSDRightsRow(BaseModel):
    raw: dict
    bas_dt: str | None = None
    crno: str | None = None
    stck_issu_cmpy_nm: str | None = None   # 주식발행회사명
    stck_issu_rcd_nm: str | None = None    # 발행사유명
    rgt_exert_rcd: str | None = None       # 권리행사사유코드
    rgt_exert_rcd_nm: str | None = None    # 권리행사사유명
    rgt_exert_sttg_dt: str | None = None   # 권리행사 시작일
    rgt_exert_ed_dt: str | None = None     # 권리행사 종료일
    nmls_lck_sttg_dt: str | None = None    # 명부폐쇄 시작일
    nmls_lck_ed_dt: str | None = None      # 명부폐쇄 종료일


class KSDRightsResponse(BaseModel):
    rows: list[KSDRightsRow]


@app.get("/ksd/rights-schedule", response_model=KSDRightsResponse)
def get_ksd_rights_schedule(
    bas_dt: str | None = Query(None, description="기준일 YYYYMMDD"),
    begin_dt: str | None = Query(None, description="시작일 YYYYMMDD"),
    end_dt: str | None = Query(None, description="종료일 YYYYMMDD"),
    crno: str | None = Query(None, description="법인등록번호"),
) -> KSDRightsResponse:
    try:
        rows_raw = _ksd_client().get_rights_schedule(
            bas_dt=bas_dt, begin_dt=begin_dt, end_dt=end_dt, crno=crno
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KSDRightsResponse(rows=[
        KSDRightsRow(
            raw=r,
            bas_dt=r.get("basDt"),
            crno=r.get("crno"),
            stck_issu_cmpy_nm=r.get("stckIssuCmpyNm"),
            stck_issu_rcd_nm=r.get("stckIssuRcdNm"),
            rgt_exert_rcd=r.get("rgtExertRcd"),
            rgt_exert_rcd_nm=r.get("rgtExertRcdNm"),
            rgt_exert_sttg_dt=r.get("rgtExertSttgDt"),
            rgt_exert_ed_dt=r.get("rgtExertEdDt"),
            nmls_lck_sttg_dt=r.get("nmlsLckSttgDt"),
            nmls_lck_ed_dt=r.get("nmlsLckEdDt"),
        )
        for r in rows_raw
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Options Analytics
# ═══════════════════════════════════════════════════════════════════════════════


class OptionsGreeksResponse(BaseModel):
    option_type: str
    spot: float
    strike: float
    expiry_days: int
    rate: float
    vol: float
    price: float
    intrinsic_value: float
    time_value: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class OptionsChainRow(BaseModel):
    strike: float
    call_price: float
    call_delta: float
    call_gamma: float
    call_theta: float
    call_vega: float
    put_price: float
    put_delta: float
    put_gamma: float
    put_theta: float
    put_vega: float


class OptionsChainResponse(BaseModel):
    spot: float
    expiry_days: int
    rate: float
    vol: float
    rows: list[OptionsChainRow]


class OptionsIvSurfaceResponse(BaseModel):
    spot: float
    rate: float
    atm_vol: float
    strikes: list[float]
    expiry_days: list[int]
    iv_surface: list[list[float]]


@app.get("/options/greeks", response_model=OptionsGreeksResponse)
def get_options_greeks(
    option_type: str = Query(..., description="call or put"),
    spot: float = Query(..., gt=0),
    strike: float = Query(..., gt=0),
    expiry_days: int = Query(..., ge=0),
    rate: float = Query(0.05),
    vol: float = Query(..., gt=0),
) -> OptionsGreeksResponse:
    if option_type not in ("call", "put"):
        raise HTTPException(status_code=400, detail="option_type must be 'call' or 'put'")
    T = expiry_days / 365.0
    price = bs_price(spot, strike, T, rate, vol, option_type)
    greeks = bs_greeks(spot, strike, T, rate, vol, option_type)
    intrinsic = max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    return OptionsGreeksResponse(
        option_type=option_type,
        spot=spot,
        strike=strike,
        expiry_days=expiry_days,
        rate=rate,
        vol=vol,
        price=round(price, 4),
        intrinsic_value=round(intrinsic, 4),
        time_value=round(price - intrinsic, 4),
        **{k: round(v, 6) for k, v in greeks.items()},
    )


@app.get("/options/chain", response_model=OptionsChainResponse)
def get_options_chain(
    spot: float = Query(..., gt=0),
    expiry_days: int = Query(..., ge=1),
    rate: float = Query(0.05),
    vol: float = Query(..., gt=0),
    strikes: str | None = Query(None, description="Comma-separated strikes. Default: 9 strikes ±20% of spot."),
) -> OptionsChainResponse:
    if strikes:
        try:
            ks = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid strikes format") from exc
    else:
        ks = [round(spot * m, 2) for m in np.linspace(0.80, 1.20, 9)]
    rows = bs_chain(spot, expiry_days, rate, vol, ks)
    return OptionsChainResponse(
        spot=spot,
        expiry_days=expiry_days,
        rate=rate,
        vol=vol,
        rows=[OptionsChainRow(**r) for r in rows],
    )


@app.get("/options/iv-surface", response_model=OptionsIvSurfaceResponse)
def get_options_iv_surface(
    spot: float = Query(..., gt=0),
    rate: float = Query(0.05),
    atm_vol: float = Query(..., gt=0),
    skew: float = Query(0.1),
    smile: float = Query(0.3),
) -> OptionsIvSurfaceResponse:
    result = bs_iv_surface(spot, rate, atm_vol, skew, smile)
    return OptionsIvSurfaceResponse(
        spot=spot,
        rate=rate,
        atm_vol=atm_vol,
        **result,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Futures Analytics
# ═══════════════════════════════════════════════════════════════════════════════


class FuturesPriceResponse(BaseModel):
    spot: float
    rate: float
    convenience_yield: float
    expiry_days: int
    price: float
    basis: float
    basis_pct: float
    annualized_carry: float
    market_structure: str


class FuturesCalendarRow(BaseModel):
    expiry_days: int
    price: float
    basis: float
    basis_pct: float
    annualized_carry: float
    market_structure: str


class FuturesCalendarResponse(BaseModel):
    spot: float
    rate: float
    convenience_yield: float
    rows: list[FuturesCalendarRow]


class FuturesRollRow(BaseModel):
    front_days: int
    back_days: int
    front_price: float
    back_price: float
    roll_cost: float
    roll_cost_pct: float
    annualized_roll_yield: float
    days_to_roll: int


class FuturesRollResponse(BaseModel):
    spot: float
    rate: float
    convenience_yield: float
    front_days: int
    rolls: list[FuturesRollRow]


@app.get("/futures/price", response_model=FuturesPriceResponse)
def get_futures_price(
    spot: float = Query(..., gt=0),
    rate: float = Query(0.05),
    convenience_yield: float = Query(0.02),
    expiry_days: int = Query(..., ge=0),
) -> FuturesPriceResponse:
    T = expiry_days / 365.0
    fp = futures_price(spot, rate, convenience_yield, T)
    return FuturesPriceResponse(
        spot=spot,
        rate=rate,
        convenience_yield=convenience_yield,
        expiry_days=expiry_days,
        **fp,
    )


@app.get("/futures/calendar", response_model=FuturesCalendarResponse)
def get_futures_calendar(
    spot: float = Query(..., gt=0),
    rate: float = Query(0.05),
    convenience_yield: float = Query(0.02),
) -> FuturesCalendarResponse:
    expiry_days = [30, 60, 90, 120, 180, 252, 360]
    rows = futures_calendar(spot, rate, convenience_yield, expiry_days)
    return FuturesCalendarResponse(
        spot=spot,
        rate=rate,
        convenience_yield=convenience_yield,
        rows=[FuturesCalendarRow(**r) for r in rows],
    )


@app.get("/futures/roll", response_model=FuturesRollResponse)
def get_futures_roll(
    spot: float = Query(..., gt=0),
    rate: float = Query(0.05),
    convenience_yield: float = Query(0.02),
    front_days: int = Query(30, ge=1),
) -> FuturesRollResponse:
    back_days_list = [d for d in [60, 90, 120, 180, 252] if d > front_days]
    if not back_days_list:
        raise HTTPException(status_code=400, detail="front_days must be less than 252")
    rolls = [futures_roll(spot, rate, convenience_yield, front_days, bd) for bd in back_days_list]
    return FuturesRollResponse(
        spot=spot,
        rate=rate,
        convenience_yield=convenience_yield,
        front_days=front_days,
        rolls=[FuturesRollRow(**r) for r in rolls],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Forex Analytics
# ═══════════════════════════════════════════════════════════════════════════════


class ForexForwardResponse(BaseModel):
    spot: float
    rate_domestic: float
    rate_foreign: float
    days: int
    forward: float
    forward_points: float
    forward_points_pct: float
    annualized_differential: float
    market_structure: str


class ForexCurveRow(BaseModel):
    tenor_days: int
    forward: float
    forward_points: float
    forward_points_pct: float
    annualized_differential: float
    market_structure: str


class ForexCurveResponse(BaseModel):
    spot: float
    rate_domestic: float
    rate_foreign: float
    rows: list[ForexCurveRow]


class ForexCarryResponse(BaseModel):
    spot: float
    rate_domestic: float
    rate_foreign: float
    days: int
    forward: float
    carry_rate: float
    net_carry_pct: float
    breakeven_move_pct: float
    favorable: bool
    uip_expected_move_pct: float


@app.get("/forex/forward", response_model=ForexForwardResponse)
def get_forex_forward(
    spot: float = Query(..., gt=0),
    rate_domestic: float = Query(0.05),
    rate_foreign: float = Query(0.03),
    days: int = Query(..., ge=0),
) -> ForexForwardResponse:
    T = days / 365.0
    fp = fx_forward(spot, rate_domestic, rate_foreign, T)
    return ForexForwardResponse(
        spot=spot,
        rate_domestic=rate_domestic,
        rate_foreign=rate_foreign,
        days=days,
        **fp,
    )


@app.get("/forex/curve", response_model=ForexCurveResponse)
def get_forex_curve(
    spot: float = Query(..., gt=0),
    rate_domestic: float = Query(0.05),
    rate_foreign: float = Query(0.03),
) -> ForexCurveResponse:
    tenors = [7, 30, 60, 90, 180, 365]
    rows = fx_curve(spot, rate_domestic, rate_foreign, tenors)
    return ForexCurveResponse(
        spot=spot,
        rate_domestic=rate_domestic,
        rate_foreign=rate_foreign,
        rows=[ForexCurveRow(**r) for r in rows],
    )


@app.get("/forex/carry", response_model=ForexCarryResponse)
def get_forex_carry(
    spot: float = Query(..., gt=0),
    rate_domestic: float = Query(0.05),
    rate_foreign: float = Query(0.03),
    days: int = Query(..., ge=1),
) -> ForexCarryResponse:
    T = days / 365.0
    fc = fx_carry(spot, rate_domestic, rate_foreign, T)
    return ForexCarryResponse(
        spot=spot,
        rate_domestic=rate_domestic,
        rate_foreign=rate_foreign,
        days=days,
        **fc,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AI Strategy Advisor
# ═══════════════════════════════════════════════════════════════════════════════


class AiRecommendResponse(BaseModel):
    instrument_id: str
    strategy: str
    params: dict
    reasoning: str


@app.get("/ai/strategy-recommend", response_model=AiRecommendResponse)
def ai_strategy_recommend(
    instrument_id: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> AiRecommendResponse:
    start_ns = date_to_ns(start.isoformat())
    end_ns = date_to_ns(end.isoformat())

    try:
        bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid instrument_id: {exc}") from exc

    catalog = ParquetDataCatalog(CATALOG_PATH)
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]

    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {instrument_id!r} in [{start}, {end}]",
        )

    try:
        result = recommend_strategy(bars, instrument_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI recommendation failed: {exc}") from exc

    return AiRecommendResponse(
        instrument_id=instrument_id,
        strategy=result["strategy"],
        params=result["params"],
        reasoning=result["reasoning"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Crypto Analytics (Hyperliquid)
# ═══════════════════════════════════════════════════════════════════════════════

import time as _time


class CryptoAsset(BaseModel):
    name: str
    mid_price: float
    mark_price: float
    funding_rate_8h: float    # % per 8h (e.g. 0.01 = 0.01% per 8h)
    funding_rate: float       # annualized % (funding_rate_8h * 3 * 365)
    open_interest: float
    day_change_pct: float
    day_volume: float


class CryptoAssetsResponse(BaseModel):
    assets: list[CryptoAsset]
    count: int


class CryptoCandle(BaseModel):
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    num_trades: int


class CryptoCandlesResponse(BaseModel):
    coin: str
    interval: str
    candles: list[CryptoCandle]


class BookLevel(BaseModel):
    price: float
    size: float
    num_orders: int


class CryptoBookResponse(BaseModel):
    coin: str
    bids: list[BookLevel]   # top 20, best (highest) first
    asks: list[BookLevel]   # top 20, best (lowest) first
    mid_price: float
    spread: float
    spread_pct: float


@app.get("/crypto/assets", response_model=CryptoAssetsResponse)
def get_crypto_assets() -> CryptoAssetsResponse:
    try:
        universe, ctxs = get_meta_and_ctxs()
        assets = []
        for meta, ctx in zip(universe, ctxs):
            name = meta["name"]
            mid_price = float(ctx.get("midPx") or "0")
            prev_day_px = float(ctx.get("prevDayPx") or "0")
            day_change_pct = ((mid_price - prev_day_px) / prev_day_px * 100) if prev_day_px else 0.0
            funding_8h = float(ctx.get("funding") or "0")
            assets.append(CryptoAsset(
                name=name,
                mid_price=round(mid_price, 6),
                mark_price=round(float(ctx.get("markPx") or "0"), 6),
                funding_rate_8h=round(funding_8h * 100, 6),
                funding_rate=round(funding_8h * 100 * 3 * 365, 4),
                open_interest=round(float(ctx.get("openInterest") or "0"), 4),
                day_change_pct=round(day_change_pct, 4),
                day_volume=round(float(ctx.get("dayNtlVlm") or "0"), 2),
            ))
        return CryptoAssetsResponse(assets=assets, count=len(assets))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/crypto/candles", response_model=CryptoCandlesResponse)
def get_crypto_candles(
    coin: str = Query("BTC"),
    interval: Literal["1d", "4h", "1h", "15m"] = Query("1d"),
    days: int = Query(90, ge=1, le=365),
) -> CryptoCandlesResponse:
    try:
        end_ms = int(_time.time() * 1000)
        start_ms = end_ms - days * 24 * 3600 * 1000
        raw = get_candles(coin.strip().upper(), interval, start_ms, end_ms)
        candles = [
            CryptoCandle(
                time_ms=c["t"],
                open=float(c["o"]),
                high=float(c["h"]),
                low=float(c["l"]),
                close=float(c["c"]),
                volume=float(c["v"]),
                num_trades=int(c["n"]),
            )
            for c in raw
        ]
        return CryptoCandlesResponse(coin=coin.strip().upper(), interval=interval, candles=candles)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/crypto/book", response_model=CryptoBookResponse)
def get_crypto_book(
    coin: str = Query("BTC"),
) -> CryptoBookResponse:
    try:
        raw = get_l2_book(coin.strip().upper())
        levels = raw.get("levels", [[], []])
        bid_raw = levels[0] if len(levels) > 0 else []
        ask_raw = levels[1] if len(levels) > 1 else []
        bids = [BookLevel(price=float(l["px"]), size=float(l["sz"]), num_orders=int(l["n"])) for l in bid_raw[:20]]
        asks = [BookLevel(price=float(l["px"]), size=float(l["sz"]), num_orders=int(l["n"])) for l in ask_raw[:20]]
        mid_price = (bids[0].price + asks[0].price) / 2 if bids and asks else 0.0
        spread = asks[0].price - bids[0].price if bids and asks else 0.0
        spread_pct = (spread / mid_price * 100) if mid_price > 0 else 0.0
        return CryptoBookResponse(
            coin=coin.strip().upper(),
            bids=bids,
            asks=asks,
            mid_price=round(mid_price, 6),
            spread=round(spread, 6),
            spread_pct=round(spread_pct, 4),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════════
# IB Market Data
# ═══════════════════════════════════════════════════════════════════════════════

class IBBarOut(BaseModel):
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class IBBarsResponse(BaseModel):
    symbol: str
    asset_type: str
    bars: list[IBBarOut]
    count: int


def _bar_date_to_ms(date) -> int:
    if isinstance(date, str):
        fmt = "%Y%m%d" if len(date) == 8 and date.isdigit() else "%Y-%m-%d"
        d = dt.datetime.strptime(date, fmt).replace(tzinfo=dt.timezone.utc)
    elif isinstance(date, dt.datetime):
        d = date if date.tzinfo else date.replace(tzinfo=dt.timezone.utc)
    else:
        d = dt.datetime.combine(date, dt.time.min, tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


@app.get("/ib/bars", response_model=IBBarsResponse)
async def get_ib_bars(
    symbol: str = Query(...),
    asset_type: Literal["stock", "forex", "future", "option", "crypto"] = Query("stock"),
    end_date: str = Query(""),
    duration: str = Query("1 Y"),
    exchange: str = Query(""),
    expiry: str = Query(""),
    strike: float = Query(0.0),
    right: Literal["C", "P"] = Query("C"),
) -> IBBarsResponse:
    ib_client = IBClient(client_id=random.randint(1, 899))
    try:
        sym = symbol.strip().upper()
        if asset_type == "stock":
            raw = await ib_client.get_daily_bars(sym, end_date, duration)
            label = f"{sym}.STOCK"
        elif asset_type == "forex":
            raw = await ib_client.get_daily_bars_forex(sym, end_date, duration)
            label = f"{sym}.FOREX"
        elif asset_type == "future":
            raw = await ib_client.get_daily_bars_future(
                sym, exchange.strip().upper(), expiry.strip(), end_date, duration
            )
            label = f"{sym}.{exchange.strip().upper()}.FUTURE"
        elif asset_type == "option":
            raw = await ib_client.get_daily_bars_option(
                sym, expiry.strip(), strike, right, end_date, duration
            )
            label = f"{sym}.{expiry.strip()}.{strike}.{right}.OPTION"
        else:
            raw = await ib_client.get_daily_bars_crypto(sym, end_date, duration)
            label = f"{sym}.CRYPTO"
        bars = [
            IBBarOut(
                ts_ms=_bar_date_to_ms(b.date),
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in raw
        ]
        return IBBarsResponse(symbol=label, asset_type=asset_type, bars=bars, count=len(bars))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if ib_client._ib.isConnected():
            ib_client._ib.disconnect()


# ── KR Universe Search ──────────────────────────────────────────────────────────


class KRSearchResult(BaseModel):
    code: str
    name: str
    market: str


class KRSearchResponse(BaseModel):
    query: str
    results: list[KRSearchResult]
    count: int


@app.get("/search/kr", response_model=KRSearchResponse)
def search_kr(q: str = Query(..., min_length=1)):
    try:
        results = search_universe(q.strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return KRSearchResponse(
        query=q,
        results=[KRSearchResult(**r) for r in results],
        count=len(results),
    )


# ── KR On-demand OHLCV ──────────────────────────────────────────────────────────


class KRBar(BaseModel):
    date: str
    open: int
    high: int
    low: int
    close: int
    volume: int


class KRBarsResponse(BaseModel):
    code: str
    name: str
    bars: list[KRBar]
    count: int


@app.get("/kr/bars", response_model=KRBarsResponse)
def get_kr_bars(
    code: str = Query(..., min_length=1, max_length=6),
    days: int = Query(default=365, ge=1, le=3650),
):
    code = code.strip().zfill(6)
    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        raise HTTPException(status_code=503, detail="KIS credentials not configured")

    end_date = dt.date.today().strftime("%Y%m%d")
    start_date = (dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d")

    try:
        kis_client = KISClient(app_key=app_key, app_secret=app_secret)
        rows = kis_client.get_daily_price(code, start_date, end_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not rows:
        raise HTTPException(status_code=404, detail=f"no bars found for code={code!r}")

    name = code
    try:
        universe = _get_kr_universe()
        match = next((item for item in universe if item["code"] == code), None)
        if match:
            name = match["name"]
    except Exception:
        pass

    try:
        bars = [
            KRBar(
                date=row["stck_bsop_date"],
                open=int(row["stck_oprc"] or 0),
                high=int(row["stck_hgpr"] or 0),
                low=int(row["stck_lwpr"] or 0),
                close=int(row["stck_clpr"] or 0),
                volume=int(row["acml_vol"] or 0),
            )
            for row in rows
        ]
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"malformed KIS bar data: {exc}")
    return KRBarsResponse(code=code, name=name, bars=bars, count=len(bars))


# ── US Symbol Search ────────────────────────────────────────────────────────────

from ib_async import IB


class USSearchResult(BaseModel):
    symbol: str
    name: str
    sec_type: str
    exchange: str
    currency: str


class USSearchResponse(BaseModel):
    query: str
    results: list[USSearchResult]
    count: int


@app.get("/search/us", response_model=USSearchResponse)
async def search_us(q: str = Query(..., min_length=1)):
    q = q.strip()
    ib = IB()
    try:
        await ib.connectAsync("127.0.0.1", 7497, clientId=random.randint(450, 899))
        descs = await ib.reqMatchingSymbolsAsync(q)
        results = [
            USSearchResult(
                symbol=d.contract.symbol,
                name=d.contract.description or "",
                sec_type=d.contract.secType,
                exchange=d.contract.primaryExch or d.contract.exchange or "",
                currency=d.contract.currency,
            )
            for d in descs
        ]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if ib.isConnected():
            ib.disconnect()
    return USSearchResponse(query=q, results=results, count=len(results))


# ── KIS Live Streaming ──────────────────────────────────────────────────────────

from backends.kis.ws_client import KISWebSocketClient
from backends.kis.ws_auth import get_approval_key


def _parse_kis_tick(message: str) -> dict | None:
    """Parse KIS H0STCNT0 real-time trade message into a JSON-serialisable dict.

    Returns None for JSON ack/ping messages and non-trade TR IDs.

    KIS sends two message types over the WebSocket:
    - JSON objects (start with '{'): subscription acks and heartbeats — skip.
    - Pipe-delimited strings: "{ctrl}|{tr_id}|{count}|{data_block}"
      where data_block fields are '^'-separated.

    H0STCNT0 data field indices (0-based):
      0=code, 1=time(HHMMSS), 2=price, 3=change_abs, 4=change_sign,
      5=change_rate_pct, 12=trade_volume, 13=total_volume
    change_sign: '1'/'2'=up (+), '4'/'5'=down (-), '3'=flat (0)
    """
    if message.startswith("{"):
        return None

    parts = message.split("|")
    if len(parts) < 4:
        return None

    tr_id = parts[1]
    if tr_id != "H0STCNT0":
        return None

    fields = parts[3].split("^")
    if len(fields) < 14:
        return None

    try:
        change_sign = fields[4]
        sign = 1 if change_sign in ("1", "2") else (-1 if change_sign in ("4", "5") else 0)
        return {
            "code": fields[0],
            "time": fields[1],
            "price": int(fields[2]),
            "change": int(fields[3]) * sign,
            "change_rate": float(fields[5]),
            "trade_volume": int(fields[12]),
            "total_volume": int(fields[13]),
        }
    except (ValueError, IndexError):
        return None


@app.websocket("/ws/live/{code}")
async def ws_live(websocket: WebSocket, code: str) -> None:
    await websocket.accept()

    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        await websocket.send_json({"error": "KIS credentials not configured"})
        await websocket.close()
        return

    code = code.strip().upper()
    stream = None
    try:
        approval_key = get_approval_key(app_key, app_secret)
        kis_ws_client = KISWebSocketClient(approval_key)
        stream = kis_ws_client.stream_trades(code)
        async for message in stream:
            parsed = _parse_kis_tick(message)
            if parsed:
                await websocket.send_json(parsed)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"error": str(exc)})
            await websocket.close()
        except Exception:
            pass
    finally:
        if stream is not None:
            await stream.aclose()


# ── Spawner ───────────────────────────────────────────────────────────────────

class ConditionInfo(BaseModel):
    rule_index: int
    combinator: str
    condition_count: int
    indicators: list[str]


class SpawnValidationError(BaseModel):
    rule_index: int
    error: str


class SpawnValidateRequest(BaseModel):
    spawn_rules: list[dict]


class SpawnValidateResponse(BaseModel):
    valid: bool
    errors: list[SpawnValidationError]
    rules: list[ConditionInfo]


class TriggerEvent(BaseModel):
    rule_index: int
    trigger_date: str  # YYYY-MM-DD


class SpawnEvaluateRequest(BaseModel):
    spawn_rules: list[dict]
    instrument_id: str
    start: str  # YYYY-MM-DD
    end: str    # YYYY-MM-DD


class SpawnEvaluateResponse(BaseModel):
    instrument_id: str
    start: str
    end: str
    bar_count: int
    trigger_events: list[TriggerEvent]


@app.post("/spawner/validate", response_model=SpawnValidateResponse)
def validate_spawn_rules(req: SpawnValidateRequest) -> SpawnValidateResponse:
    errors: list[SpawnValidationError] = []
    infos: list[ConditionInfo] = []

    for i, rule in enumerate(req.spawn_rules):
        try:
            condition_dict = rule.get("condition", {})
            condition_set = ConditionParser.parse(condition_dict)
            # Verify each indicator operand has a registry builder (catches
            # cases where SUPPORTED_INDICATORS and _BUILDERS are out of sync)
            for comparison in condition_set.comparisons:
                for operand in [comparison.left, comparison.right]:
                    if hasattr(operand, "indicator") and operand.indicator not in _INDICATOR_BUILDERS:
                        raise ValueError(
                            f"indicator {operand.indicator!r} has no registry builder"
                        )
            indicators = sorted({
                c.left.indicator
                for c in condition_set.comparisons
                if hasattr(c.left, "indicator")
            } | {
                c.right.indicator
                for c in condition_set.comparisons
                if hasattr(c.right, "indicator")
            })
            infos.append(
                ConditionInfo(
                    rule_index=i,
                    combinator=condition_set.combinator,
                    condition_count=len(condition_set.comparisons),
                    indicators=indicators,
                )
            )
        except (ValueError, KeyError) as exc:
            errors.append(SpawnValidationError(rule_index=i, error=str(exc)))

    return SpawnValidateResponse(valid=not errors, errors=errors, rules=infos)


@app.post("/spawner/evaluate", response_model=SpawnEvaluateResponse)
def evaluate_spawn_rules(req: SpawnEvaluateRequest) -> SpawnEvaluateResponse:
    # Parse all conditions first (fail fast on invalid rules)
    condition_sets = []
    for i, rule in enumerate(req.spawn_rules):
        try:
            condition_sets.append(ConditionParser.parse(rule.get("condition", {})))
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"rule {i}: {exc}") from exc

    # Fetch bars from catalog
    try:
        instrument_id = InstrumentId.from_str(req.instrument_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid instrument_id: {exc}") from exc

    start_ns = date_to_ns(req.start)
    end_ns = date_to_ns(req.end)

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(instrument_id))
    all_bars = catalog.bars(bar_types=[bar_type_str])
    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]

    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {req.instrument_id!r} in [{req.start}, {req.end}]",
        )

    # Build one evaluator per rule
    evaluators = [
        {
            "rule_index": i,
            "evaluator": ConditionEvaluator(cs, IndicatorRegistry()),
            "triggered": False,
        }
        for i, cs in enumerate(condition_sets)
    ]

    trigger_events: list[TriggerEvent] = []
    for bar in bars:
        for entry in evaluators:
            if entry["triggered"]:
                continue
            entry["evaluator"].on_bar(bar)
            if entry["evaluator"].evaluate():
                entry["triggered"] = True
                trigger_date = dt.datetime.fromtimestamp(
                    bar.ts_event / 1e9, tz=dt.timezone.utc
                ).strftime("%Y-%m-%d")
                trigger_events.append(
                    TriggerEvent(rule_index=entry["rule_index"], trigger_date=trigger_date)
                )

    return SpawnEvaluateResponse(
        instrument_id=req.instrument_id,
        start=req.start,
        end=req.end,
        bar_count=len(bars),
        trigger_events=trigger_events,
    )


# ── Orders ────────────────────────────────────────────────────────────────────


def _compute_unrealized_pnl(
    position: str,
    qty: float,
    last_price: float | None,
    entry_price: float | None,
) -> float | None:
    if entry_price is None or last_price is None or position == "FLAT":
        return None
    return (last_price - entry_price) * qty * (1.0 if position == "LONG" else -1.0)


class KROrderRequest(BaseModel):
    code: str
    side: str           # "BUY" | "SELL"
    quantity: int
    order_type: str     # "MARKET" | "LIMIT"
    price: int | None = None  # required for LIMIT


class KROrderResponse(BaseModel):
    order_id: str
    status: str
    filled: float
    remaining: float


class KRCancelRequest(BaseModel):
    code: str
    quantity: int


class USOrderRequest(BaseModel):
    symbol: str           # e.g. "AAPL"
    side: str             # "BUY" | "SELL"
    quantity: int
    order_type: str       # "MARKET" | "LIMIT"
    limit_price: float | None = None  # required for LIMIT


class USOrderResponse(BaseModel):
    order_id: int
    status: str
    filled: float
    remaining: float


class BotLiveEntry(BaseModel):
    bot_id: str
    name: str
    instrument_id: str
    running: bool
    position: str
    qty: float
    last_price: float | None
    last_signal: str | None
    error: str | None
    entry_price: float | None = None
    unrealized_pnl: float | None = None


class AllBotsStatusResponse(BaseModel):
    bots: list[BotLiveEntry]


@app.post("/orders/kr", response_model=KROrderResponse)
def place_kr_order(req: KROrderRequest) -> KROrderResponse:
    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    cano = os.environ.get("KIS_CANO", "")
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "")
    if not all([app_key, app_secret, cano, acnt_prdt_cd]):
        raise HTTPException(status_code=503, detail="KIS credentials not configured")
    if req.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail=f"invalid side: {req.side!r}")
    if req.order_type not in ("MARKET", "LIMIT"):
        raise HTTPException(status_code=400, detail=f"invalid order_type: {req.order_type!r}")
    if req.order_type == "LIMIT" and req.price is None:
        raise HTTPException(status_code=400, detail="price required for LIMIT order")
    try:
        order_client = KISOrderClient(app_key, app_secret, cano, acnt_prdt_cd)
        result = order_client.place_order(
            req.code, req.side, req.quantity, req.order_type, req.price
        )
        return KROrderResponse(**result)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise HTTPException(status_code=503, detail="KIS unreachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/orders/kr/{order_no}/cancel", response_model=KROrderResponse)
def cancel_kr_order(order_no: str, req: KRCancelRequest) -> KROrderResponse:
    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    cano = os.environ.get("KIS_CANO", "")
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "")
    if not all([app_key, app_secret, cano, acnt_prdt_cd]):
        raise HTTPException(status_code=503, detail="KIS credentials not configured")
    try:
        order_client = KISOrderClient(app_key, app_secret, cano, acnt_prdt_cd)
        result = order_client.cancel_order(order_no, req.code, req.quantity)
        return KROrderResponse(**result)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise HTTPException(status_code=503, detail="KIS unreachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/orders/kr/{order_no}/status", response_model=KROrderResponse)
def get_kr_order_status(
    order_no: str,
    date: str = Query(..., description="Order date YYYYMMDD"),
) -> KROrderResponse:
    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    cano = os.environ.get("KIS_CANO", "")
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "")
    if not all([app_key, app_secret, cano, acnt_prdt_cd]):
        raise HTTPException(status_code=503, detail="KIS credentials not configured")
    try:
        order_client = KISOrderClient(app_key, app_secret, cano, acnt_prdt_cd)
        result = order_client.get_order_status(date, order_no)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise HTTPException(status_code=503, detail="KIS unreachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"order {order_no!r} not found for date {date!r}")
    return KROrderResponse(**result)


@app.post("/orders/us", response_model=USOrderResponse)
async def place_us_order(req: USOrderRequest) -> USOrderResponse:
    if req.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail=f"invalid side: {req.side!r}")
    if req.order_type not in ("MARKET", "LIMIT"):
        raise HTTPException(status_code=400, detail=f"invalid order_type: {req.order_type!r}")
    if req.order_type == "LIMIT" and req.limit_price is None:
        raise HTTPException(status_code=400, detail="limit_price required for LIMIT order")
    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=int(os.environ.get("IB_PORT", "7497")),
        client_id=int(os.environ.get("IB_MANUAL_ORDER_CLIENT_ID", "10")),
    )
    try:
        result = await ib_client.place_order(
            req.symbol, req.side, req.quantity, req.order_type, req.limit_price
        )
        return USOrderResponse(**result)
    except (ConnectionRefusedError, OSError) as exc:
        raise HTTPException(status_code=503, detail="IB TWS not reachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await ib_client.close()


@app.post("/orders/us/{order_id}/cancel", response_model=USOrderResponse)
async def cancel_us_order(order_id: int) -> USOrderResponse:
    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=int(os.environ.get("IB_PORT", "7497")),
        client_id=int(os.environ.get("IB_MANUAL_ORDER_CLIENT_ID", "10")),
    )
    try:
        result = await ib_client.cancel_order(order_id)
        return USOrderResponse(**result)
    except (ConnectionRefusedError, OSError) as exc:
        raise HTTPException(status_code=503, detail="IB TWS not reachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await ib_client.close()


@app.get("/orders/us/{order_id}/status", response_model=USOrderResponse)
async def get_us_order_status(order_id: int) -> USOrderResponse:
    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=int(os.environ.get("IB_PORT", "7497")),
        client_id=int(os.environ.get("IB_MANUAL_ORDER_CLIENT_ID", "10")),
    )
    try:
        result = await ib_client.get_order_status(order_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"IB order {order_id!r} not found")
        return USOrderResponse(**result)
    except HTTPException:
        raise
    except (ConnectionRefusedError, OSError) as exc:
        raise HTTPException(status_code=503, detail="IB TWS not reachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await ib_client.close()


# Note: /bots/all-live-status works because all dynamic bot GET routes are
# 3-segment (e.g., /bots/{bot_id}/live-status). There is no 2-segment
# GET /bots/{bot_id} route, so this endpoint is matched first. FastAPI matches
# routes in declaration order, NOT literal-path-first. WARNING: Adding a
# GET /bots/{bot_id} route before this endpoint would cause "all-live-status"
# to be incorrectly captured as a bot_id.
@app.get("/bots/all-live-status", response_model=AllBotsStatusResponse)
def get_all_bots_live_status() -> AllBotsStatusResponse:
    bots = _load_bots()
    all_statuses = live_engine.get_all_statuses()
    entries = []
    for bot_id, bot_data in bots.items():
        status = all_statuses.get(bot_id)
        if status is not None:
            pnl = _compute_unrealized_pnl(
                status.position, status.qty, status.last_price, status.entry_price
            )
            entries.append(
                BotLiveEntry(
                    bot_id=bot_id,
                    name=bot_data["name"],
                    instrument_id=bot_data["instrument_id"],
                    running=True,
                    position=status.position,
                    qty=status.qty,
                    last_price=status.last_price,
                    last_signal=status.last_signal,
                    error=status.error,
                    entry_price=status.entry_price,
                    unrealized_pnl=pnl,
                )
            )
        else:
            entries.append(
                BotLiveEntry(
                    bot_id=bot_id,
                    name=bot_data["name"],
                    instrument_id=bot_data["instrument_id"],
                    running=False,
                    position="FLAT",
                    qty=0.0,
                    last_price=None,
                    last_signal=None,
                    error=None,
                    entry_price=None,
                    unrealized_pnl=None,
                )
            )
    return AllBotsStatusResponse(bots=entries)


# ── Bot detail / trade log / signal log endpoints ──────────────────────────────
# IMPORTANT: GET /bots/{bot_id} is placed here, AFTER /bots/all-live-status,
# so that "all-live-status" is not captured as a bot_id.

@app.get("/bots/{bot_id}", response_model=BotRecord)
def get_bot(bot_id: str) -> BotRecord:
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")
    return BotRecord(**bots[bot_id])


@app.get("/bots/{bot_id}/trades", response_model=BotTradeLogResponse)
def get_bot_trade_log(bot_id: str) -> BotTradeLogResponse:
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")
    state = live_engine._running.get(bot_id)
    trades = [ClosedTrade(**t) for t in (state.closed_trades if state else [])]
    return BotTradeLogResponse(bot_id=bot_id, trades=trades)


@app.get("/bots/{bot_id}/signals", response_model=BotSignalLogResponse)
def get_bot_signal_log(bot_id: str) -> BotSignalLogResponse:
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"bot {bot_id!r} not found")
    state = live_engine._running.get(bot_id)
    signals = [SignalEntry(**s) for s in (state.signal_log if state else [])]
    return BotSignalLogResponse(bot_id=bot_id, signals=signals)


# ── Alert System ──────────────────────────────────────────────
_ALERT_CONDITION_TYPES = frozenset({
    "price_above", "price_below", "pnl_above", "pnl_below",
    "bot_error", "bot_stopped",
})
_THRESHOLD_REQUIRED = frozenset({"price_above", "price_below", "pnl_above", "pnl_below"})

class CreateAlertRuleRequest(BaseModel):
    label: str
    condition_type: str
    bot_id: str
    threshold: float | None = None

class AlertRuleOut(BaseModel):
    id: str
    label: str
    condition_type: str
    bot_id: str
    threshold: float | None
    created_at: str

class AlertRulesResponse(BaseModel):
    rules: list[AlertRuleOut]

class TriggeredAlertOut(BaseModel):
    rule_id: str
    rule_label: str
    condition_type: str
    bot_id: str
    detail: str
    triggered_at: str

class TriggeredAlertsResponse(BaseModel):
    triggered: list[TriggeredAlertOut]

_alert_rules: dict[str, AlertRuleOut] = {}
_triggered_alerts: list[TriggeredAlertOut] = []
_MAX_TRIGGERED = 200
_DEDUP_SECONDS = 300
_alert_lock = threading.Lock()


def _evaluate_alert_condition(
    rule: AlertRuleOut,
    statuses: dict[str, "BotStatus"],
) -> tuple[bool, str]:
    status = statuses.get(rule.bot_id)
    t = rule.threshold

    if rule.condition_type == "price_above":
        if status is None or status.last_price is None:
            return False, ""
        if status.last_price > t:
            return True, f"price {status.last_price:.4f} > {t:.4f}"
        return False, ""

    if rule.condition_type == "price_below":
        if status is None or status.last_price is None:
            return False, ""
        if status.last_price < t:
            return True, f"price {status.last_price:.4f} < {t:.4f}"
        return False, ""

    if rule.condition_type == "pnl_above":
        if status is None:
            return False, ""
        pnl = _compute_unrealized_pnl(
            status.position, status.qty, status.last_price, status.entry_price
        )
        if pnl is None:
            return False, ""
        if pnl > t:
            return True, f"unrealized PnL {pnl:.2f} > {t:.2f}"
        return False, ""

    if rule.condition_type == "pnl_below":
        if status is None:
            return False, ""
        pnl = _compute_unrealized_pnl(
            status.position, status.qty, status.last_price, status.entry_price
        )
        if pnl is None:
            return False, ""
        if pnl < t:
            return True, f"unrealized PnL {pnl:.2f} < {t:.2f}"
        return False, ""

    if rule.condition_type == "bot_error":
        if status is None:
            return False, ""
        if status.error:
            return True, f"error: {status.error}"
        return False, ""

    if rule.condition_type == "bot_stopped":
        if status is None:
            return True, "bot not running"
        return False, ""

    return False, ""


def _recently_triggered(rule_id: str) -> bool:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=_DEDUP_SECONDS)
    for entry in _triggered_alerts:
        if entry.rule_id == rule_id:
            try:
                if dt.datetime.fromisoformat(entry.triggered_at) > cutoff:
                    return True
            except ValueError:
                pass
    return False


@app.post("/alerts/rules", response_model=AlertRuleOut, status_code=201)
def create_alert_rule(req: CreateAlertRuleRequest) -> AlertRuleOut:
    if req.condition_type not in _ALERT_CONDITION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown condition_type: {req.condition_type!r}")
    if req.condition_type in _THRESHOLD_REQUIRED and req.threshold is None:
        raise HTTPException(status_code=400, detail="threshold required for this condition_type")
    rule = AlertRuleOut(
        id=str(uuid.uuid4()),
        label=req.label,
        condition_type=req.condition_type,
        bot_id=req.bot_id,
        threshold=req.threshold,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    _alert_rules[rule.id] = rule
    return rule


@app.get("/alerts/rules", response_model=AlertRulesResponse)
def list_alert_rules() -> AlertRulesResponse:
    return AlertRulesResponse(rules=list(_alert_rules.values()))


@app.delete("/alerts/rules/{rule_id}", status_code=204)
def delete_alert_rule(rule_id: str) -> None:
    if rule_id not in _alert_rules:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id!r} not found")
    del _alert_rules[rule_id]


@app.get("/alerts/triggered", response_model=TriggeredAlertsResponse)
def get_triggered_alerts() -> TriggeredAlertsResponse:
    statuses = live_engine.get_all_statuses()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    with _alert_lock:
        for rule in list(_alert_rules.values()):
            triggered, detail = _evaluate_alert_condition(rule, statuses)
            if triggered and not _recently_triggered(rule.id):
                entry = TriggeredAlertOut(
                    rule_id=rule.id,
                    rule_label=rule.label,
                    condition_type=rule.condition_type,
                    bot_id=rule.bot_id,
                    detail=detail,
                    triggered_at=now_iso,
                )
                _triggered_alerts.append(entry)
                if len(_triggered_alerts) > _MAX_TRIGGERED:
                    _triggered_alerts.pop(0)
        snapshot = list(reversed(_triggered_alerts))
    return TriggeredAlertsResponse(triggered=snapshot)
