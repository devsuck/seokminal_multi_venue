import asyncio
import datetime as dt
import json
import os
import random
import statistics as _stats
import sys
import threading
import uuid
from pathlib import Path
from typing import Literal

# 레포 루트를 절대경로로 고정 — cwd 변경이나 sys.path 변조가 있어도
# 로컬 패키지(hyperliquid/ 등) 임포트가 깨지지 않게 방어.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import requests

import numpy as np

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pydantic import BaseModel, Field

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
from live_engine.risk_guard import (
    DailyPnLTracker,
    RiskConfig,
    RiskViolation,
    validate_option_expiry,
    validate_order,
)
from api_server.order_audit import read_recent as read_order_audit, record_order
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
    # 기본 로컬 개발. 배포(클라우드) 시 CORS_ORIGINS 환경변수(쉼표구분)로 도메인 지정.
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    # 폰에서 LAN(192.168/10/172.16-31)·Tailscale(100.x) IP:3000 접근 허용.
    allow_origin_regex=r"http://(192\.168|10|172\.(1[6-9]|2\d|3[01])|100)\.[0-9.]+:3000",
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

    # 카탈로그에 없는 종목이면 yfinance에서 자동 적재 (US/KR/크립토)
    from api_server.auto_ingest import ensure_bars as _ensure_bars
    _ingest = _ensure_bars(CATALOG_PATH, instrument_id)

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    all_bars = catalog.bars(bar_types=[bar_type_str])

    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        hint = f" (자동 수집 실패: {_ingest['error']})" if _ingest.get("error") else ""
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {instrument_id!r} in range [{start}, {end}]{hint}",
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
    cost_bps: float = Query(5.0, ge=0, le=100, description="체결당 거래비용(슬리피지+수수료) bps. 왕복 2회 차감."),
) -> BacktestResponse:
    if strategy not in SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported strategy {strategy!r}, expected one of {SUPPORTED_STRATEGIES}",
        )

    # 카탈로그에 없는 종목이면 yfinance에서 자동 적재 (US/KR/크립토)
    from api_server.auto_ingest import ensure_bars as _ensure_bars
    _ensure_bars(CATALOG_PATH, instrument_id)

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
            simple_params = {"fast": fast, "slow": slow, "signal_period": signal_period, "trade_size": trade_size, "cost_bps": cost_bps}
        elif strategy == "rsi":
            simple_params = {"period": period, "oversold": oversold, "overbought": overbought, "trade_size": trade_size, "cost_bps": cost_bps}
        else:  # xgb
            simple_params = {
                "train_ratio": xgb_train_ratio,
                "n_estimators": xgb_n_estimators,
                "max_depth": xgb_max_depth,
                "learning_rate": xgb_learning_rate,
                "trade_size": trade_size,
                "cost_bps": cost_bps,
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


def _iso_to_ecos_period(iso_date: str, cycle: str) -> str:
    """ISO 'YYYY-MM-DD' → ECOS StatisticSearch가 요구하는 주기별 포맷.

    ECOS는 시리즈 주기(cycle: Y/Q/M/D)마다 다른 날짜 포맷을 요구한다(예: 월별은
    'YYYYMM'). 프론트는 다른 시계열 API(FRED 등)와 동일하게 ISO 날짜만 알면 되도록
    이 경계에서 변환한다."""
    y, m, d = iso_date.split("-")
    if cycle == "Y":
        return y
    if cycle == "Q":
        return f"{y}Q{(int(m) - 1) // 3 + 1}"
    if cycle == "D":
        return f"{y}{m}{d}"
    return f"{y}{m}"  # "M" (기본)


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
        cycle = meta.get("cycle", "M")
        observations = client.get_series_by_id(
            series_id, _iso_to_ecos_period(start, cycle), _iso_to_ecos_period(end, cycle),
        )
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
        def _f(*keys: str) -> float | None:
            for k in keys:
                v = r.get(k, "")
                if v and str(v).strip():
                    try: return float(str(v).replace(",", ""))
                    except (TypeError, ValueError): pass
            return None
        rows.append(KRXIndexRow(
            bas_dd=r.get("BAS_DD") or r.get("basDd", bas_dd),
            idx_nm=r.get("IDX_NM") or r.get("idxNm") or r.get("idx_nm"),
            clpr=_f("CLSPRC_IDX", "clpr", "cls_prc"),
            vs=_f("CMPPREVDD_IDX", "vs"),
            flt_rt=_f("FLUC_RT", "fltRt", "flt_rt"),
            opn_prc=_f("OPNPRC_IDX", "opnPrc", "opn_prc"),
            hgpr=_f("HGPRC_IDX", "hgpr"),
            lwpr=_f("LWPRC_IDX", "lwpr"),
            acc_trdvol=_f("ACC_TRDVOL", "accTrdvol", "acc_trdvol"),
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


class NlConditionRequest(BaseModel):
    text: str


class NlConditionResponse(BaseModel):
    combinator: str
    comparisons: list[dict]
    fast: int
    slow: int


@app.post("/ai/nl-to-condition", response_model=NlConditionResponse)
def ai_nl_to_condition(body: NlConditionRequest) -> NlConditionResponse:
    from ai_strategy.condition_advisor import nl_to_condition
    try:
        result = nl_to_condition(body.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"조건식 변환 실패: {exc}") from exc
    return NlConditionResponse(**result)


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
    interval: Literal["1m", "15m", "1h", "4h", "1d", "1M"] = Query("1d"),
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


IB_BAR_SIZES = {
    "1 min", "2 mins", "3 mins", "5 mins", "10 mins", "15 mins", "20 mins", "30 mins",
    "1 hour", "2 hours", "3 hours", "4 hours", "8 hours",
    "1 day", "1 week", "1 month",
}


@app.get("/ib/bars", response_model=IBBarsResponse)
async def get_ib_bars(
    symbol: str = Query(...),
    asset_type: Literal["stock", "forex", "future", "option", "crypto"] = Query("stock"),
    end_date: str = Query(""),
    duration: str = Query("1 Y"),
    bar_size: str = Query("1 day"),
    exchange: str = Query(""),
    expiry: str = Query(""),
    strike: float = Query(0.0),
    right: Literal["C", "P"] = Query("C"),
) -> IBBarsResponse:
    if bar_size not in IB_BAR_SIZES:
        raise HTTPException(status_code=400, detail=f"Invalid bar_size '{bar_size}'. Valid: {sorted(IB_BAR_SIZES)}")
    ib_client = IBClient(client_id=random.randint(1, 899))
    try:
        sym = symbol.strip().upper()
        if asset_type == "stock":
            raw = await ib_client.get_daily_bars(sym, end_date, duration, bar_size)
            label = f"{sym}.STOCK"
        elif asset_type == "forex":
            raw = await ib_client.get_daily_bars_forex(sym, end_date, duration, bar_size)
            label = f"{sym}.FOREX"
        elif asset_type == "future":
            raw = await ib_client.get_daily_bars_future(
                sym, exchange.strip().upper(), expiry.strip(), end_date, duration, bar_size
            )
            label = f"{sym}.{exchange.strip().upper()}.FUTURE"
        elif asset_type == "option":
            raw = await ib_client.get_daily_bars_option(
                sym, expiry.strip(), strike, right, end_date, duration, bar_size
            )
            label = f"{sym}.{expiry.strip()}.{strike}.{right}.OPTION"
        else:
            raw = await ib_client.get_daily_bars_crypto(sym, end_date, duration, bar_size)
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


# ── IB Options Chain ─────────────────────────────────────────────────────────────


@app.get("/ib/options/chain")
async def ib_options_chain(symbol: str = Query(..., description="US 주식 ticker")):
    """주식 옵션 체인 (지연 데이터, OPRA 구독 불필요).
    Returns: {expiry: [{strike, right, bid, ask, last, volume, iv, delta}]}
    """
    import random
    ib_client = IBClient(client_id=random.randint(500, 599))
    try:
        chain = await ib_client.get_option_chain(symbol.upper())
        return {"symbol": symbol.upper(), "chain": chain}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IB 옵션 체인 오류: {exc}")


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
        await ib.connectAsync(os.environ.get("IB_HOST", "127.0.0.1"), 7497,
                              clientId=random.randint(450, 899), timeout=15)
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


# ── IB Live Streaming ─────────────────────────────────────────────────────────


def _serialize_ib_tick(symbol: str, tick) -> dict:
    """Serialise an ib_async TickByTickAllLast into a JSON-safe dict.

    ``tick.time`` is a timezone-aware datetime; emit epoch seconds so the
    frontend can format locally. price/size come through as plain numbers.
    """
    return {
        "symbol": symbol,
        "time": tick.time.timestamp() if tick.time is not None else None,
        "price": float(tick.price),
        "size": float(tick.size),
        "exchange": tick.exchange or "",
    }


# IB error codes that mean "no ticks will ever arrive on this stream" — relay
# them to the client so the widget stops waiting. 354/10168/10167 = market data
# not subscribed; 162/200 = historical/contract problems; 504 = not connected.
_IB_FATAL_ERROR_CODES = {162, 200, 354, 504, 10167, 10168, 10197}


@app.websocket("/ws/ib/live/{symbol}")
async def ws_ib_live(websocket: WebSocket, symbol: str) -> None:
    """Stream IB tick-by-tick trades for a US equity symbol.

    Requires a running TWS/IB Gateway (default 127.0.0.1:7497). When the
    gateway is unreachable, stream_trades' connectAsync times out and raises,
    and we relay the error to the client and close — the widget then shows
    offline. If the gateway is up but the account lacks a market-data
    subscription, IB emits an async error event (e.g. 354) rather than
    raising; we forward those fatal codes so the widget doesn't hang waiting
    for ticks that never come. Each connection uses a random client_id to
    allow concurrent symbols.
    """
    await websocket.accept()

    symbol = symbol.strip().upper()
    client = IBClient(client_id=random.randint(900, 999))
    loop = asyncio.get_running_loop()
    error_queue: asyncio.Queue[str] = asyncio.Queue()

    def _on_ib_error(reqId, errorCode, errorString, contract):  # noqa: N803 (ib_async signature)
        if errorCode in _IB_FATAL_ERROR_CODES:
            loop.call_soon_threadsafe(error_queue.put_nowait, errorString)

    client._ib.errorEvent += _on_ib_error

    stream = None
    stream_task = None
    error_task = None
    try:
        stream = client.stream_trades(symbol)
        stream_task = asyncio.ensure_future(stream.__anext__())
        error_task = asyncio.ensure_future(error_queue.get())

        while True:
            done, _ = await asyncio.wait(
                {stream_task, error_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if error_task in done:
                await websocket.send_json({"error": error_task.result()})
                await websocket.close()
                break
            if stream_task in done:
                tick = stream_task.result()  # raises StopAsyncIteration when stream ends
                await websocket.send_json(_serialize_ib_tick(symbol, tick))
                stream_task = asyncio.ensure_future(stream.__anext__())
    except (WebSocketDisconnect, StopAsyncIteration):
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"error": str(exc)})
            await websocket.close()
        except Exception:
            pass
    finally:
        client._ib.errorEvent -= _on_ib_error
        for task in (stream_task, error_task):
            if task is not None and not task.done():
                task.cancel()
        if stream is not None:
            await stream.aclose()
        try:
            if client._ib.isConnected():
                client._ib.disconnect()
        except Exception:
            pass


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
    quantity: int = Field(gt=0)
    order_type: str     # "MARKET" | "LIMIT"
    price: int | None = None  # required for LIMIT
    paper: bool = True  # True=모의(KIS_MOCK), False=실전(KIS)


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
    quantity: int = Field(gt=0)
    order_type: str       # "MARKET" | "LIMIT"
    limit_price: float | None = None  # required for LIMIT
    paper: bool = True    # True=Alpaca 페이퍼, False=IB(TWS) 실계좌


class USOrderResponse(BaseModel):
    order_id: int
    status: str
    filled: float
    remaining: float


class OptionOrderRequest(BaseModel):
    symbol: str           # 기초자산 ticker, e.g. "AAPL"
    expiry: str            # YYYYMMDD
    strike: float
    right: Literal["C", "P"]
    side: str              # "BUY" | "SELL"
    quantity: int = Field(gt=0)  # 계약 수 (1계약=기초자산 100주)
    order_type: str        # "MARKET" | "LIMIT"
    limit_price: float | None = None  # required for LIMIT
    paper: bool = True     # True=IB paper(7497), False=IB live(7496) — 옵션은 항상 IB


class OptionOrderResponse(BaseModel):
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


# Shared firm-wide risk state: one config snapshot (env-driven) and one
# realized-PnL ledger feed the pre-trade guard on every order path.
daily_pnl_tracker = DailyPnLTracker()


def _check_risk(
    *, side: str, quantity: float, price_estimate: float | None,
    current_position_qty: int = 0, option_expiry: str | None = None,
) -> None:
    """Run the pre-trade risk guard; translate a violation into HTTP 422.

    Re-reads RiskConfig from env each call so limit changes (incl. the kill
    switch) take effect without a restart. ``option_expiry`` (YYYYMMDD) is
    only passed by the options order path and gates on MIN_OPTION_DTE.
    """
    cfg = RiskConfig.from_env()
    try:
        validate_order(
            side=side,
            quantity=quantity,
            price_estimate=price_estimate,
            current_position_qty=current_position_qty,
            day_realized_pnl=daily_pnl_tracker.realized(),
            config=cfg,
        )
        if option_expiry is not None:
            validate_option_expiry(option_expiry, cfg)
    except RiskViolation as exc:
        raise HTTPException(status_code=422, detail=f"risk check failed: {exc}") from exc


@app.get("/trading/mode")
def get_trading_mode() -> dict:
    """Report paper/live mode per venue plus the active risk limits.

    The frontend uses this to badge the orders page and force extra
    confirmation before sending against a live account. IB mode is inferred
    from the configured port (7497 = paper default, 7496 = live default);
    a non-standard port is reported as "unknown" since only the TWS login
    truly decides.
    """
    ib_port = int(os.environ.get("IB_PORT", "7497"))
    ib_mode = "paper" if ib_port == 7497 else "live" if ib_port == 7496 else "unknown"
    kr_mode = "paper" if os.environ.get("KIS_MOCK", "true").lower() == "true" else "live"
    alpaca_mode = "paper" if os.environ.get("ALPACA_PAPER", "true").lower() == "true" else "live"
    cfg = RiskConfig.from_env()
    return {
        "venues": {
            "US": {"mode": ib_mode, "ib_port": ib_port},
            "KR": {"mode": kr_mode},
            "ALPACA": {"mode": alpaca_mode},
            "HL": {"mode": "live"},  # Hyperliquid uses a real key; paper is per-order
        },
        "risk": {
            "max_order_qty": cfg.max_order_qty,
            "max_order_notional": cfg.max_order_notional,
            "max_position_qty": cfg.max_position_qty,
            "daily_loss_limit": cfg.daily_loss_limit,
            "kill_switch": cfg.kill_switch,
            "min_option_dte": cfg.min_option_dte,
        },
        "any_live": "live" in (ib_mode, kr_mode, alpaca_mode),
    }


@app.get("/orders/audit")
def get_orders_audit(limit: int = 100) -> dict:
    """Return the recent persisted order audit trail (newest last)."""
    return {"entries": read_order_audit(limit=limit)}


@app.post("/orders/kr", response_model=KROrderResponse)
def place_kr_order(req: KROrderRequest) -> KROrderResponse:
    # Route to 모의(KIS_MOCK) or 실전(KIS) creds + server by the paper flag.
    if req.paper:
        app_key = os.environ.get("KIS_MOCK_APP_KEY", "")
        app_secret = os.environ.get("KIS_MOCK_APP_SECRET", "")
        cano = os.environ.get("KIS_MOCK_CANO", "")
    else:
        app_key = os.environ.get("KIS_APP_KEY", "")
        app_secret = os.environ.get("KIS_APP_SECRET", "")
        cano = os.environ.get("KIS_CANO", "")
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "")
    if not all([app_key, app_secret, cano, acnt_prdt_cd]):
        raise HTTPException(status_code=503, detail=f"KIS {'모의' if req.paper else '실전'} credentials not configured")
    if req.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail=f"invalid side: {req.side!r}")
    if req.order_type not in ("MARKET", "LIMIT"):
        raise HTTPException(status_code=400, detail=f"invalid order_type: {req.order_type!r}")
    if req.order_type == "LIMIT" and req.price is None:
        raise HTTPException(status_code=400, detail="price required for LIMIT order")
    _check_risk(side=req.side, quantity=req.quantity, price_estimate=req.price)
    try:
        order_client = KISOrderClient(app_key, app_secret, cano, acnt_prdt_cd, mock=req.paper)
        result = order_client.place_order(
            req.code, req.side, req.quantity, req.order_type, req.price
        )
        record_order(venue="KR", request=req.model_dump(), result=result, status="submitted")
        return KROrderResponse(**result)
    except (requests.ConnectionError, requests.Timeout) as exc:
        record_order(venue="KR", request=req.model_dump(), result=None, status="error")
        raise HTTPException(status_code=503, detail="KIS unreachable") from exc
    except Exception as exc:
        record_order(venue="KR", request=req.model_dump(), result=None, status="error")
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
    _check_risk(side=req.side, quantity=req.quantity, price_estimate=req.limit_price)

    # US 라우팅: 페이퍼=Alpaca(무제한·무TWS), 실계좌=IB(TWS 7496).
    if req.paper:
        try:
            from api_server.router_autopilot import place_order as _alpaca_order, OrderRequest as _AlpacaReq
            r = _alpaca_order(_AlpacaReq(symbol=req.symbol, side=req.side.lower(),
                                        qty=float(req.quantity), type=req.order_type.lower(),
                                        limit_price=req.limit_price, paper=True))
            record_order(venue="US", request=req.model_dump(), result=r, status="submitted")
            # Alpaca order id is a UUID (str); USOrderResponse.order_id is int → 0 placeholder.
            return USOrderResponse(order_id=0, status=r["status"],
                                   filled=float(r.get("filled_qty", 0.0)),
                                   remaining=float(req.quantity - r.get("filled_qty", 0.0)))
        except HTTPException:
            raise
        except Exception as exc:
            record_order(venue="US", request=req.model_dump(), result=None, status="error")
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=7496,  # live TWS
        client_id=int(os.environ.get("IB_MANUAL_ORDER_CLIENT_ID", "10")),
    )
    try:
        result = await ib_client.place_order(
            req.symbol, req.side, req.quantity, req.order_type, req.limit_price
        )
        record_order(venue="US", request=req.model_dump(), result=result, status="submitted")
        return USOrderResponse(**result)
    except (ConnectionRefusedError, OSError) as exc:
        record_order(venue="US", request=req.model_dump(), result=None, status="error")
        raise HTTPException(status_code=503, detail="IB TWS not reachable") from exc
    except Exception as exc:
        record_order(venue="US", request=req.model_dump(), result=None, status="error")
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


@app.post("/orders/options", response_model=OptionOrderResponse)
async def place_option_order(req: OptionOrderRequest) -> OptionOrderResponse:
    if req.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail=f"invalid side: {req.side!r}")
    if req.order_type not in ("MARKET", "LIMIT"):
        raise HTTPException(status_code=400, detail=f"invalid order_type: {req.order_type!r}")
    if req.order_type == "LIMIT" and req.limit_price is None:
        raise HTTPException(status_code=400, detail="limit_price required for LIMIT order")
    # 1계약=기초자산 100주 → 리스크 한도(달러 기준)는 계약당 프리미엄*100으로 환산.
    price_estimate = req.limit_price * 100 if req.limit_price is not None else None
    _check_risk(side=req.side, quantity=req.quantity, price_estimate=price_estimate,
                option_expiry=req.expiry)

    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=7497 if req.paper else 7496,
        client_id=int(os.environ.get("IB_OPTION_ORDER_CLIENT_ID", "12")),
    )
    try:
        result = await ib_client.place_option_order(
            req.symbol, req.expiry, req.strike, req.right,
            req.side, req.quantity, req.order_type, req.limit_price,
        )
        record_order(venue="US_OPTIONS", request=req.model_dump(), result=result, status="submitted")
        return OptionOrderResponse(**result)
    except (ConnectionRefusedError, OSError) as exc:
        record_order(venue="US_OPTIONS", request=req.model_dump(), result=None, status="error")
        raise HTTPException(status_code=503, detail="IB TWS not reachable") from exc
    except Exception as exc:
        record_order(venue="US_OPTIONS", request=req.model_dump(), result=None, status="error")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await ib_client.close()


@app.post("/orders/options/{order_id}/cancel", response_model=OptionOrderResponse)
async def cancel_option_order(order_id: int) -> OptionOrderResponse:
    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=int(os.environ.get("IB_PORT", "7497")),
        client_id=int(os.environ.get("IB_OPTION_ORDER_CLIENT_ID", "12")),
    )
    try:
        result = await ib_client.cancel_order(order_id)
        return OptionOrderResponse(**result)
    except (ConnectionRefusedError, OSError) as exc:
        raise HTTPException(status_code=503, detail="IB TWS not reachable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await ib_client.close()


@app.get("/orders/options/{order_id}/status", response_model=OptionOrderResponse)
async def get_option_order_status(order_id: int) -> OptionOrderResponse:
    ib_client = IBOrderClient(
        host=os.environ.get("IB_HOST", "127.0.0.1"),
        port=int(os.environ.get("IB_PORT", "7497")),
        client_id=int(os.environ.get("IB_OPTION_ORDER_CLIENT_ID", "12")),
    )
    try:
        result = await ib_client.get_order_status(order_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"IB order {order_id!r} not found")
        return OptionOrderResponse(**result)
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


# ── /insider ───────────────────────────────────────────────────────────────────

from insider.dart_client import search_company as _dart_search, get_executive_stock_changes as _dart_trades, get_recent_kr_insider_feed as _dart_recent, get_recent_kr_corporate_actions as _dart_corp_actions, action_weight as _dart_weight
from insider.congress_client import get_congress_trades as _congress_trades
from insider.gov_spending_client import get_recent_contracts as _gov_contracts


class GovContract(BaseModel):
    recipient: str
    amount: float
    agency: str | None = None
    description: str | None = None
    start_date: str | None = None
    award_id: str | None = None


@app.get("/insider/gov-contracts", response_model=list[GovContract])
def insider_gov_contracts(days: int = Query(30, ge=1, le=180), limit: int = Query(40, ge=10, le=100)) -> list[GovContract]:
    """미국 연방정부 계약 낙찰 (USASpending) — 기업 단위."""
    try:
        rows = _gov_contracts(days=days, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"USASpending error: {exc}") from exc
    return [GovContract(**r) for r in rows]


class CongressTrade(BaseModel):
    chamber: str
    trade_date: str
    disclosure_date: str
    reporter: str
    district: str | None = None
    owner: str | None = None
    ticker: str | None = None
    asset: str | None = None
    trade_type: str
    amount: str | None = None
    link: str | None = None


@app.get("/insider/congress", response_model=list[CongressTrade])
def insider_congress(limit: int = Query(80, ge=10, le=200)) -> list[CongressTrade]:
    """미국 의회(상·하원) 의원 주식 매매 신고 (STOCK Act)."""
    try:
        rows = _congress_trades(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"congress feed error: {exc}") from exc
    return [CongressTrade(**r) for r in rows]
from insider.edgar_client import get_form4_transactions as _edgar_trades, get_recent_form4_feed as _edgar_recent


class DartCompany(BaseModel):
    corp_code: str
    corp_name: str
    stock_code: str


class InsiderTrade(BaseModel):
    trade_date: str
    reporter: str
    trade_type: str          # BUY / SELL / RIGHTS_ISSUE / PAID_IN / CANCELLATION / HOLD_REPORT
    shares_change: int | None = None
    shares: float | None = None
    price_per_share: float | None = None
    value_usd: float | None = None
    shares_owned_after: float | None = None
    shares_total: int | None = None
    ownership_pct: float | None = None
    report_type: str | None = None
    corp_name: str | None = None
    ticker: str | None = None
    issuer: str | None = None
    role: str | None = None          # KR: 직책 (대표이사, 사외이사 등)
    event_cause: str | None = None   # KR: 증감원인 (장내매수, 무상증자 등)
    dart_url: str | None = None      # KR: 공시 원문 링크


@app.get("/insider/kr/search", response_model=list[DartCompany])
def insider_kr_search(q: str = Query(..., min_length=1)) -> list[DartCompany]:
    try:
        results = _dart_search(q)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenDART error: {exc}") from exc
    return [DartCompany(**r) for r in results]


@app.get("/insider/kr", response_model=list[InsiderTrade])
def insider_kr(
    corp_code: str = Query(...),
    days: int = Query(180, ge=1, le=730),
) -> list[InsiderTrade]:
    end_de = dt.date.today().strftime("%Y%m%d")
    bgn_de = (dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d")
    try:
        rows = _dart_trades(corp_code, bgn_de, end_de)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenDART error: {exc}") from exc
    return [
        InsiderTrade(
            trade_date=r["rcept_dt"],
            reporter=r["reporter"],
            trade_type=r["trade_type"],
            shares_change=r["shares_change"],
            shares_total=r["shares_total"],
            ownership_pct=r["ownership_pct"],
            report_type=r["report_type"],
            corp_name=r["corp_name"],
            role=r.get("role") or None,
            event_cause=r.get("event_cause") or None,
            dart_url=r.get("dart_url") or None,
        )
        for r in rows
    ]


@app.get("/insider/us", response_model=list[InsiderTrade])
def insider_us(
    ticker: str = Query(..., min_length=1, max_length=10),
    days: int = Query(90, ge=1, le=365),
) -> list[InsiderTrade]:
    # Finnhub 우선 (SEC가 해외 IP를 차단해 EDGAR 직접 조회 불가한 환경 대응),
    # 실패 시 EDGAR 폴백.
    rows: list[dict] = []
    errors: list[str] = []
    try:
        from insider.finnhub_client import get_insider_transactions as _fh_trades
        rows = _fh_trades(ticker.upper(), days)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Finnhub: {exc}")
    if not rows:
        try:
            rows = _edgar_trades(ticker.upper(), days)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"SEC EDGAR: {exc}")
    if not rows and errors:
        raise HTTPException(status_code=502, detail=" / ".join(errors))
    if not rows and days <= 365:
        # ticker might not exist
        raise HTTPException(status_code=404, detail=f"No Form 4 filings found for {ticker!r}")
    return [
        InsiderTrade(
            trade_date=r["transaction_date"],
            reporter=r["reporter"],
            trade_type=r["trade_type"],
            shares=r.get("shares"),
            price_per_share=r.get("price_per_share"),
            value_usd=r.get("value_usd"),
            shares_owned_after=r.get("shares_owned_after"),
            ticker=r.get("ticker"),
            issuer=r.get("issuer"),
        )
        for r in rows
    ]


@app.get("/insider/us/recent", response_model=list[InsiderTrade])
def insider_us_recent(
    days: int = Query(7, ge=1, le=30),
    max_filings: int = Query(40, ge=5, le=100),
) -> list[InsiderTrade]:
    # Finnhub 유니버스 피드 우선, 실패 시 EDGAR 전시장 피드 폴백.
    rows = []
    errors = []
    try:
        from insider.finnhub_client import get_recent_feed as _fh_recent
        rows = _fh_recent(days=days, max_filings=max_filings)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Finnhub: {exc}")
    if not rows:
        try:
            rows = _edgar_recent(days=days, max_filings=max_filings)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"SEC EDGAR: {exc}")
            if errors:
                raise HTTPException(status_code=502, detail=" / ".join(errors)) from exc
    return [
        InsiderTrade(
            trade_date=r["transaction_date"],
            reporter=r["reporter"],
            trade_type=r["trade_type"],
            shares=r.get("shares"),
            price_per_share=r.get("price_per_share"),
            value_usd=r.get("value_usd"),
            shares_owned_after=r.get("shares_owned_after"),
            ticker=r.get("ticker"),
            issuer=r.get("issuer"),
        )
        for r in rows
    ]


@app.get("/insider/kr/recent", response_model=list[InsiderTrade])
def insider_kr_recent(
    days: int = Query(30, ge=1, le=180),
    max_corps: int = Query(40, ge=5, le=100),
) -> list[InsiderTrade]:
    """매매 판단에 영향 주는 기업행위만: 유상/무상증자, 자기주식 취득·소각.
    (보유자 소유상황보고는 제외)"""
    try:
        rows = _dart_corp_actions(days=days, max_items=max_corps)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenDART error: {exc}") from exc
    return [
        InsiderTrade(
            trade_date=r["trade_date"],
            reporter=r["reporter"],
            trade_type=r["trade_type"],
            report_type=r.get("report_type"),
            corp_name=r.get("corp_name"),
            ticker=r.get("ticker"),
            event_cause=r.get("event_cause") or None,
            dart_url=r.get("dart_url") or None,
        )
        for r in rows
    ]


# ── Copy-Trade Autopilot (페이퍼) ────────────────────────────────────────────────
# 스마트머니(의회·내부자) 공개 매수 신고를 페이퍼 계좌에 자동/수동 미러링.
# AI 예측 아님 — 규칙 기반 추종. 실행은 Alpaca 페이퍼(무료·무한).

class CopySignal(BaseModel):
    source: str        # "congress" | "insider"
    name: str          # 의원/내부자 이름
    role: str | None = None
    ticker: str
    trade_type: str    # "BUY"
    date: str          # 거래일
    disclosed: str | None = None  # 공시일
    amount: str | None = None
    link: str | None = None


def _is_buy(t: str | None) -> bool:
    return bool(t) and any(k in t.lower() for k in ("buy", "purchase", "매수"))


@app.get("/copytrade/signals", response_model=list[CopySignal])
def copytrade_signals(limit: int = Query(60, ge=10, le=200)) -> list[CopySignal]:
    """의회 + 미국 내부자 '매수' 신호 집계 (US 티커만, 페이퍼 미러 대상)."""
    out: list[CopySignal] = []
    # 의회
    try:
        for r in _congress_trades(limit=limit):
            tk = (r.get("ticker") or "").strip().upper()
            if tk and tk.isalpha() and _is_buy(r.get("trade_type")):
                out.append(CopySignal(
                    source="congress", name=r.get("reporter", ""), role=r.get("chamber"),
                    ticker=tk, trade_type="BUY", date=r.get("trade_date", ""),
                    disclosed=r.get("disclosure_date"), amount=r.get("amount"), link=r.get("link"),
                ))
    except Exception:  # noqa: BLE001
        pass
    # 미국 내부자 (EDGAR Form4)
    try:
        for r in _edgar_recent(days=14, max_filings=60):
            tk = (r.get("ticker") or "").strip().upper()
            if tk and tk.isalpha() and _is_buy(r.get("trade_type")):
                amt = r.get("value_usd")
                out.append(CopySignal(
                    source="insider", name=r.get("reporter", ""), role=r.get("issuer"),
                    ticker=tk, trade_type="BUY", date=r.get("transaction_date", ""),
                    amount=f"${amt:,.0f}" if amt else None,
                ))
    except Exception:  # noqa: BLE001
        pass
    # 최신순
    out.sort(key=lambda s: s.disclosed or s.date, reverse=True)
    return out[:limit]


class MirrorRequest(BaseModel):
    ticker: str
    notional: float = 500.0  # 미러 1건당 페이퍼 매수 금액 (USD)


@app.post("/copytrade/mirror")
def copytrade_mirror(body: MirrorRequest) -> dict:
    """페이퍼 계좌에 notional 시장가 매수 (Alpaca paper). 실계좌 아님."""
    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        raise HTTPException(status_code=503, detail="ALPACA 키 없음")
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    client = TradingClient(api_key=key, secret_key=sec, paper=True)
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=body.ticker.strip().upper(), notional=round(body.notional, 2),
            side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
        ))
        return {"order_id": str(order.id), "ticker": body.ticker.upper(),
                "notional": body.notional, "status": str(order.status)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"페이퍼 주문 실패: {exc}") from exc


class TraderHolding(BaseModel):
    ticker: str
    date: str
    entry: float | None = None
    current: float | None = None
    return_pct: float | None = None


class TraderCard(BaseModel):
    source: str
    name: str
    role: str | None = None
    initials: str
    num_buys: int
    avg_return_pct: float | None = None
    holdings: list[TraderHolding]


_traders_cache: dict = {}
_TRADERS_TTL = 1800  # 30분


def _initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@app.get("/copytrade/traders", response_model=list[TraderCard])
def copytrade_traders(limit: int = Query(120, ge=20, le=300)) -> list[TraderCard]:
    """매수자별 카드: 최근 매수 종목을 거래일 종가로 진입했다 가정, 현재가 대비 수익률.
    Autopilot 앱 스타일 — 인물별 트랙레코드. 30분 캐시."""
    now = _time.time()
    if "d" in _traders_cache and now - _traders_cache["t"] < _TRADERS_TTL:
        return _traders_cache["d"]

    import datetime as _d
    signals = copytrade_signals(limit=limit)
    cutoff = _d.date.today() - _d.timedelta(days=120)

    # (source,name) → [(ticker, date_str)]
    people: dict[tuple, dict] = {}
    tickers: set[str] = set()
    for s in signals:
        try:
            dt_ = _d.date.fromisoformat(s.date[:10])
        except Exception:
            continue
        if dt_ < cutoff:
            continue
        key = (s.source, s.name)
        p = people.setdefault(key, {"role": s.role, "buys": []})
        p["buys"].append((s.ticker, dt_))
        tickers.add(s.ticker)

    # 가격 배치 조회 (yfinance) — 진입(거래일 종가) + 현재(최신 종가)
    prices: dict[str, "any"] = {}
    if tickers:
        try:
            import yfinance as yf
            data = yf.download(list(tickers), start=cutoff.isoformat(), progress=False,
                               auto_adjust=True, group_by="ticker", threads=True)
            for tk in tickers:
                try:
                    closes = data[tk]["Close"].dropna() if len(tickers) > 1 else data["Close"].dropna()
                    if len(closes):
                        prices[tk] = closes
                except Exception:
                    continue
        except Exception:  # noqa: BLE001
            prices = {}

    def _price_on(tk: str, d: "any"):
        s = prices.get(tk)
        if s is None or not len(s):
            return None, None
        cur = float(s.iloc[-1])
        # 거래일 이하의 마지막 종가 = 진입가
        import pandas as _pd
        ts = _pd.Timestamp(d)
        prior = s[s.index <= ts]
        entry = float(prior.iloc[-1]) if len(prior) else float(s.iloc[0])
        return entry, cur

    cards: list[TraderCard] = []
    for (source, name), p in people.items():
        holdings = []
        rets = []
        # 종목별 최신 1건 (중복 매수 합치기)
        seen = {}
        for tk, d in sorted(p["buys"], key=lambda x: x[1], reverse=True):
            if tk in seen:
                continue
            seen[tk] = True
            entry, cur = _price_on(tk, d)
            rp = round((cur - entry) / entry * 100, 2) if entry and cur else None
            holdings.append(TraderHolding(ticker=tk, date=d.isoformat(), entry=round(entry, 2) if entry else None,
                                          current=round(cur, 2) if cur else None, return_pct=rp))
            if rp is not None:
                rets.append(rp)
        avg = round(sum(rets) / len(rets), 2) if rets else None
        cards.append(TraderCard(source=source, name=name, role=p["role"], initials=_initials(name),
                                 num_buys=len(holdings), avg_return_pct=avg, holdings=holdings))

    cards.sort(key=lambda c: (c.avg_return_pct if c.avg_return_pct is not None else -999), reverse=True)
    _traders_cache["d"] = cards
    _traders_cache["t"] = now
    return cards


@app.get("/copytrade/positions")
def copytrade_positions() -> list[dict]:
    """페이퍼 계좌 보유 포지션 (미러 성과 확인용)."""
    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        raise HTTPException(status_code=503, detail="ALPACA 키 없음")
    from alpaca.trading.client import TradingClient
    client = TradingClient(api_key=key, secret_key=sec, paper=True)
    try:
        out = []
        for p in client.get_all_positions():
            out.append({
                "ticker": p.symbol, "qty": float(p.qty),
                "avg_price": float(p.avg_entry_price), "current": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc) * 100,
            })
        return out
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"포지션 조회 실패: {exc}") from exc


@app.post("/copytrade/close/{ticker}")
def copytrade_close(ticker: str) -> dict:
    """페이퍼 포지션 전량 시장가 청산."""
    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        raise HTTPException(status_code=503, detail="ALPACA 키 없음")
    from alpaca.trading.client import TradingClient
    client = TradingClient(api_key=key, secret_key=sec, paper=True)
    try:
        order = client.close_position(ticker.strip().upper())
        return {"ticker": ticker.upper(), "status": str(getattr(order, "status", "submitted"))}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"청산 실패: {exc}") from exc


class CopyAutoExitRequest(BaseModel):
    tp_pct: float = 15.0   # 익절 임계 (+%)
    sl_pct: float = 7.0    # 손절 임계 (%)


@app.post("/copytrade/auto-exit")
def copytrade_auto_exit(body: CopyAutoExitRequest) -> dict:
    """TP/SL 규칙 일괄 적용 — 임계 초과 포지션 전부 청산.

    Alpaca 포지션엔 진입일이 없어 보유기간 규칙은 미지원(수익률 기반만).
    프론트 오토파일럿이 주기적으로 호출해 예산을 회수한다.
    """
    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        raise HTTPException(status_code=503, detail="ALPACA 키 없음")
    tp = max(float(body.tp_pct), 0.1)
    sl = max(float(body.sl_pct), 0.1)
    from alpaca.trading.client import TradingClient
    client = TradingClient(api_key=key, secret_key=sec, paper=True)
    closed: list[dict] = []
    try:
        for p in client.get_all_positions():
            plpc = float(p.unrealized_plpc) * 100
            reason = None
            if plpc >= tp:
                reason = f"익절 +{plpc:.1f}%"
            elif plpc <= -sl:
                reason = f"손절 {plpc:.1f}%"
            if reason is None:
                continue
            try:
                client.close_position(p.symbol)
                closed.append({"ticker": p.symbol, "pl_pct": round(plpc, 2), "reason": reason})
            except Exception:  # noqa: BLE001 — 개별 실패는 다음 호출에서 재시도
                continue
        return {"closed": closed, "count": len(closed)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"자동청산 실패: {exc}") from exc


# ── 페어 트레이딩 (시장중립 stat-arb) ────────────────────────────────────────────

class PairsResult(BaseModel):
    instrument_a: str
    instrument_b: str
    cointegrated: bool
    eg_pvalue: float
    hedge_ratio: float
    half_life_days: float
    total_return_pct: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    num_trades: int = 0
    win_rate: float | None = None
    zscore: list[float] = []
    tradeable: bool
    note: str


@app.get("/pairs/backtest", response_model=PairsResult)
def pairs_backtest(a: str = Query(...), b: str = Query(...), cost_bps: float = Query(5.0, ge=0, le=100)) -> PairsResult:
    """두 종목 공적분 검정 + 스프레드 z-score 백테스트(비용 반영). 시장중립."""
    catalog = ParquetDataCatalog(CATALOG_PATH)

    def _closes(iid: str) -> dict:
        bt = str(bar_type_for(InstrumentId.from_str(iid)))
        return {bar.ts_event: float(bar.close) for bar in catalog.bars(bar_types=[bt])}

    ca, cb = _closes(a), _closes(b)
    common = sorted(set(ca) & set(cb))
    if len(common) < 30:
        raise HTTPException(status_code=400, detail=f"공통 봉 부족 ({len(common)}, 30↑ 필요)")
    pa = [ca[t] for t in common]
    pb = [cb[t] for t in common]

    from pairs_trading.johansen import test_cointegration
    from pairs_trading.backtest import backtest_pairs
    coint = test_cointegration(pa, pb)
    bt = backtest_pairs(pa, pb, coint["hedge_ratio"], coint["spread"],
                        _signals_from_z(coint["zscore"]), cost_bps=cost_bps)

    cointegrated = bool(coint["cointegrated"] or coint.get("johansen_cointegrated"))
    hl = coint["half_life_days"]
    tradeable = cointegrated and 1 <= hl <= 60
    if not cointegrated:
        note = "공적분 안 됨 — 스프레드 평균회귀 신뢰 낮음. 페어 부적합"
    elif hl > 60:
        note = f"반감기 {hl}일 — 회귀 너무 느림. 부적합"
    elif hl < 1:
        note = f"반감기 {hl}일 — 너무 빠름(노이즈). 주의"
    else:
        note = f"공적분 ✓, 반감기 {hl}일 — 페어 적합"

    return PairsResult(
        instrument_a=a, instrument_b=b, cointegrated=cointegrated,
        eg_pvalue=coint["eg_pvalue"], hedge_ratio=coint["hedge_ratio"], half_life_days=hl,
        total_return_pct=bt.get("total_return_pct"), sharpe_ratio=bt.get("sharpe_ratio"),
        max_drawdown_pct=bt.get("max_drawdown_pct"), num_trades=bt.get("num_trades", 0),
        win_rate=bt.get("win_rate"), zscore=[round(z, 2) for z in coint["zscore"][-120:]],
        tradeable=tradeable, note=note,
    )


def _signals_from_z(zscore: list[float]) -> list[str]:
    out = []
    for z in zscore:
        if z > 2.0:
            out.append("sell_spread")
        elif z < -2.0:
            out.append("buy_spread")
        elif abs(z) < 0.5:
            out.append("exit")
        else:
            out.append("hold")
    return out


# ── 스마트 시그널 (레짐 게이트 + 모멘텀 팩터 + Kelly 사이징) ─────────────────────────

class SmartSignal(BaseModel):
    instrument_id: str
    verdict: str            # BUY / HOLD / AVOID
    current_regime: str     # bull_low_vol / bull_high_vol / bear_high_vol / bear_low_vol
    momentum_60d_pct: float | None = None
    price_vs_sma50_pct: float | None = None
    kelly_half: float | None = None
    vol_annual_pct: float | None = None      # 연율 변동성
    cvar_95_pct: float | None = None         # 일간 95% 조건부 VaR (꼬리손실)
    sizing_constraint: str | None = None     # 최종 비중을 묶은 제약 (kelly/vol/cvar/cap)
    suggested_position_pct: float
    notes: list[str]


@app.get("/signal/smart", response_model=SmartSignal)
def smart_signal(instrument_id: str = Query(...)) -> SmartSignal:
    """레짐(HMM) + 모멘텀 + Kelly 결합 매매 판단 + 사이징. catalog 일봉 기반."""
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))
    catalog = ParquetDataCatalog(CATALOG_PATH)
    bars = sorted(catalog.bars(bar_types=[bar_type_str]), key=lambda b: b.ts_event)
    closes = [float(b.close) for b in bars]
    if len(closes) < 60:
        raise HTTPException(status_code=400, detail=f"데이터 부족 ({len(closes)}봉, 60↑ 필요)")

    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1] > 0]
    notes: list[str] = []

    # 레짐 (HMM)
    regime = "unknown"
    try:
        from regime_filter.hmm_detector import detect_regime_hmm
        regime = detect_regime_hmm(rets)["current_regime"]
    except Exception as e:  # noqa: BLE001
        notes.append(f"레짐 계산 실패: {str(e)[:40]}")

    # 모멘텀 팩터
    mom = (closes[-1] / closes[-60] - 1) * 100 if closes[-60] > 0 else None
    sma50 = sum(closes[-50:]) / 50
    px_sma = (closes[-1] / sma50 - 1) * 100 if sma50 > 0 else None

    # Kelly (일간 수익 분포 기반)
    kelly_half = None
    try:
        from risk_analysis.kelly import compute_kelly
        kelly_half = compute_kelly(rets)["kelly_half"]
    except Exception:  # noqa: BLE001
        pass

    # 변동성(리스크패리티=변동성 타게팅) + CVaR(꼬리손실)
    import statistics as _st
    vol_d = _st.pstdev(rets) if len(rets) > 1 else 0.0
    vol_annual = vol_d * (252 ** 0.5)
    cvar95 = None
    try:
        from risk_analysis.cvar import compute_cvar
        cvar95 = compute_cvar(rets).get("cvar_95")  # 일간, 음수
    except Exception:  # noqa: BLE001
        pass

    TARGET_VOL = 0.15      # 연율 목표 변동성 (리스크패리티)
    RISK_BUDGET = 0.015    # 일간 꼬리손실 예산 (자본 1.5%)
    CAP = 0.25             # 비중 상한

    # 결합 판단
    bull = regime.startswith("bull")
    risk_off = regime == "bear_high_vol"
    mom_up = (mom or 0) > 0 and (px_sma or 0) > 0
    constraint = None

    if risk_off:
        verdict = "AVOID"; notes.append("고변동 하락 레짐 — 리스크오프"); size = 0.0
    elif bull and mom_up:
        verdict = "BUY"
        regime_mult = 1.0 if regime == "bull_low_vol" else 0.5
        kelly_frac = (kelly_half or 0.0) * regime_mult
        # 변동성 타게팅: 목표변동성/실현변동성 (0.25~1.5 클램프)
        vol_scalar = max(0.25, min(TARGET_VOL / vol_annual, 1.5)) if vol_annual > 0 else 1.0
        vol_frac = kelly_frac * vol_scalar
        # CVaR 캡: 비중 × |일간 CVaR| ≤ 일간 예산
        cvar_cap = (RISK_BUDGET / abs(cvar95)) if (cvar95 and cvar95 < 0) else CAP
        # 최종 = 셋 중 최소
        cands = {"kelly/vol": vol_frac, "cvar": cvar_cap, "cap": CAP}
        size = min(cands.values())
        constraint = min(cands, key=cands.get)
        size = round(max(size, 0.0), 4)
        notes.append(f"{regime}+모멘텀↑ → 매수. Kelly½×레짐={round(kelly_frac,4)}, 변동성타게팅×{round(vol_scalar,2)}(연변동성 {round(vol_annual*100,1)}%), CVaR캡 {round(cvar_cap,4)}")
        notes.append(f"최종 비중 = {constraint} 제약이 결정")
        if size <= 0:
            verdict = "HOLD"; notes.append("Kelly ≤ 0 (엣지 없음) → 관망")
    else:
        verdict = "HOLD"; size = 0.0
        notes.append("추세·레짐 조건 불충족 → 관망")

    return SmartSignal(
        instrument_id=instrument_id, verdict=verdict, current_regime=regime,
        momentum_60d_pct=round(mom, 2) if mom is not None else None,
        price_vs_sma50_pct=round(px_sma, 2) if px_sma is not None else None,
        kelly_half=kelly_half,
        vol_annual_pct=round(vol_annual * 100, 1),
        cvar_95_pct=round(cvar95 * 100, 2) if cvar95 is not None else None,
        sizing_constraint=constraint,
        suggested_position_pct=round(size * 100, 2), notes=notes,
    )


# ── 성과 추적 (페이퍼 계좌 equity curve + 벤치마크) ───────────────────────────────

class PerfPoint(BaseModel):
    date: str
    equity: float
    benchmark: float | None = None


class PerfSummary(BaseModel):
    points: list[PerfPoint]
    return_pct: float
    mdd_pct: float
    sharpe: float
    benchmark_return_pct: float | None = None
    excess_pct: float | None = None
    start_equity: float
    end_equity: float


@app.get("/performance/portfolio", response_model=PerfSummary)
def performance_portfolio(period: str = Query("1M")) -> PerfSummary:
    """Alpaca 페이퍼 계좌 equity curve + 수익률/MDD/Sharpe + SPY 매수보유 벤치마크."""
    import datetime as _d
    key = os.environ.get("ALPACA_API_KEY", ""); sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        raise HTTPException(status_code=503, detail="ALPACA 키 없음")
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    c = TradingClient(key, sec, paper=True)
    try:
        h = c.get_portfolio_history(GetPortfolioHistoryRequest(period=period, timeframe="1D"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Alpaca history 실패: {exc}") from exc

    ts = list(h.timestamp or [])
    eq = list(h.equity or [])
    # 계좌 개설 전 0 equity 구간 제거
    rows = [(t, e) for t, e in zip(ts, eq) if e and e > 0]
    if len(rows) < 2:
        raise HTTPException(status_code=404, detail="거래 이력 부족 (페이퍼 매매 후 다시)")
    dates = [_d.datetime.fromtimestamp(t, _d.timezone.utc).date().isoformat() for t, _ in rows]
    equity = [float(e) for _, e in rows]

    start, end = equity[0], equity[-1]
    ret = (end - start) / start * 100 if start else 0.0
    # MDD
    peak = equity[0]; mdd = 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, (e - peak) / peak * 100)
    # Sharpe (일간)
    import statistics as _st
    rets = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity)) if equity[i - 1]]
    sharpe = 0.0
    if len(rets) > 1 and _st.pstdev(rets) > 0:
        sharpe = (_st.mean(rets) / _st.pstdev(rets)) * (252 ** 0.5)

    # SPY 벤치마크 (같은 기간, 시작 equity로 정규화)
    bench_curve: dict[str, float] = {}
    bench_ret = None
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY").history(start=dates[0], end=(_d.date.fromisoformat(dates[-1]) + _d.timedelta(days=1)).isoformat(), auto_adjust=True)["Close"].dropna()
        if len(spy):
            base = float(spy.iloc[0])
            for idx, v in spy.items():
                bench_curve[idx.date().isoformat()] = start * float(v) / base
            bench_ret = (float(spy.iloc[-1]) - base) / base * 100
    except Exception:  # noqa: BLE001
        bench_curve = {}

    points = [PerfPoint(date=d, equity=round(e, 2), benchmark=round(bench_curve[d], 2) if d in bench_curve else None)
              for d, e in zip(dates, equity)]
    return PerfSummary(
        points=points, return_pct=round(ret, 2), mdd_pct=round(mdd, 2), sharpe=round(sharpe, 2),
        benchmark_return_pct=round(bench_ret, 2) if bench_ret is not None else None,
        excess_pct=round(ret - bench_ret, 2) if bench_ret is not None else None,
        start_equity=round(start, 2), end_equity=round(end, 2),
    )


# ── DART 기업행위 오토파일럿 (페이퍼/KIS 모의) ────────────────────────────────────
# 자사주 취득·소각=호재(매수), 유상증자=악재(회피). 개인 내부자 매매는 5영업일
# 지연이라 제외. 페이퍼(KIS 모의)로만 집행.

_DART_ACTION = {
    "BUYBACK":      ("자사주 취득", "BUY",   "호재"),
    "CANCELLATION": ("자사주 소각", "BUY",   "호재"),
    "PAID_IN":      ("유상증자",   "AVOID", "악재(희석)"),
    "DISPOSAL":     ("자사주 처분", "AVOID", "약악재"),
    "RIGHTS_ISSUE": ("무상증자",   "SKIP",  "중립"),
}


class DartSignal(BaseModel):
    corp_name: str
    ticker: str | None = None
    action_type: str      # BUYBACK / CANCELLATION / ...
    action_label: str     # 자사주 취득 등
    verdict: str          # BUY / AVOID / SKIP
    note: str             # 호재/악재/중립
    weight: float = 1.0   # 매수 비중 배율 (소각 1.5 / 취득 1.0 / 신탁 0.6)
    date: str             # 접수일 (YYYYMMDD)
    dart_url: str | None = None


@app.get("/dart/signals", response_model=list[DartSignal])
def dart_signals(days: int = Query(14, ge=1, le=60), max_items: int = Query(50, ge=10, le=100)) -> list[DartSignal]:
    """최근 DART 기업행위 → 매매 판정(자사주=매수/증자=회피). 최신순."""
    try:
        rows = _dart_corp_actions(days=days, max_items=max_items)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"DART error: {exc}") from exc
    out = []
    for r in rows:
        label, verdict, note = _DART_ACTION.get(r["trade_type"], (r["trade_type"], "SKIP", "—"))
        w = _dart_weight(r["trade_type"], r.get("report_type", "")) if verdict == "BUY" else 1.0
        out.append(DartSignal(
            corp_name=r.get("corp_name", ""), ticker=r.get("ticker"),
            action_type=r["trade_type"], action_label=label, verdict=verdict, note=note,
            weight=w, date=r.get("trade_date", ""), dart_url=r.get("dart_url"),
        ))
    return out


class DartMirrorRequest(BaseModel):
    code: str          # 6자리 종목코드
    krw: float = 1000000.0  # 미러 1건당 원화 예산


@app.post("/dart/mirror")
def dart_mirror(body: DartMirrorRequest) -> dict:
    """KIS 모의 계좌에 시장가 매수 (원화 예산 → 주식수). 실계좌 아님."""
    code = body.code.strip().split(".")[0]
    # 현재가 (yfinance .KS) → 주식수
    try:
        import yfinance as yf
        px = float(yf.Ticker(f"{code}.KS").history(period="1d")["Close"].iloc[-1])
    except Exception:
        px = 0.0
    if px <= 0:
        raise HTTPException(status_code=502, detail=f"{code} 현재가 조회 실패")
    qty = int(body.krw // px)
    if qty < 1:
        raise HTTPException(status_code=400, detail=f"예산 부족 (현재가 ₩{px:,.0f}, 최소 1주)")
    from backends.kis.order_client import KISOrderClient
    kk, ks, kc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""), os.environ.get("KIS_MOCK_CANO", ""))
    if not (kk and ks and kc):
        raise HTTPException(status_code=503, detail="KIS 모의 키 없음")
    kis = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=True)
    try:
        r = kis.place_order(code, "BUY", qty, "MARKET")
        return {"code": code, "qty": qty, "price": round(px, 0), "order_id": r.get("order_id"), "status": r.get("status")}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"KIS 모의 주문 실패: {exc}") from exc


@app.get("/dart/positions")
def dart_positions() -> list[dict]:
    """KIS 모의 보유 종목 (기업행위 미러 성과)."""
    from backends.kis.order_client import KISOrderClient
    kk, ks, kc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""), os.environ.get("KIS_MOCK_CANO", ""))
    if not (kk and ks and kc):
        raise HTTPException(status_code=503, detail="KIS 모의 키 없음")
    kis = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=True)
    try:
        from api_server.kr_names import name_for
        out = []
        for h in kis.get_holdings():
            entry = float(h.get("avg_price", 0) or 0)
            cur = float(h.get("current", 0) or 0)
            code = h.get("code")
            nm = h.get("name") or code
            if not nm or nm == code:      # KIS가 이름 안 주면 pykrx로 보강
                nm = name_for(code) or code
            out.append({
                "code": code, "name": nm,
                "qty": h.get("qty"), "avg_price": entry, "current": cur,
                "return_pct": round((cur - entry) / entry * 100, 2) if entry else None,
            })
        return out
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"KIS 모의 조회 실패: {exc}") from exc


# ── /calendar/economic ─────────────────────────────────────────────────────────

import time as _time

_cal_cache: dict[str, tuple[float, list]] = {}
_CAL_TTL = 60  # matches ForexFactory CDN max-age


class EconomicEvent(BaseModel):
    title: str
    country: str
    date: str
    impact: str
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


@app.get("/calendar/economic", response_model=list[EconomicEvent])
def get_economic_calendar(week: str = Query("this", pattern="^(this|next)$")) -> list[EconomicEvent]:
    now = _time.time()
    if week in _cal_cache:
        ts, data = _cal_cache[week]
        if now - ts < _CAL_TTL:
            return [EconomicEvent(**e) for e in data]

    url = f"https://nfs.faireconomy.media/ff_calendar_{week}week.json"
    try:
        resp = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (compatible; seokminal-dashboard/1.0)"},
        )
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ForexFactory fetch failed: {exc}") from exc

    raw = resp.json()
    events = []
    for item in raw:
        events.append({
            "title":    item.get("title", ""),
            "country":  item.get("country", ""),
            "date":     item.get("date", ""),
            "impact":   item.get("impact", ""),
            "forecast": item.get("forecast") or None,
            "previous": item.get("previous") or None,
            "actual":   item.get("actual") or None,
        })

    _cal_cache[week] = (now, events)
    return [EconomicEvent(**e) for e in events]


# ── /macro/fear-greed ──────────────────────────────────────────────────────────

_fg_cache: dict[str, tuple[float, dict]] = {}
_FG_TTL = 3600  # 1h — updates once/day


class FearGreedResponse(BaseModel):
    value: int
    classification: str
    timestamp: str


@app.get("/macro/fear-greed", response_model=FearGreedResponse)
def get_fear_greed() -> FearGreedResponse:
    now = _time.time()
    if "fg" in _fg_cache:
        ts, data = _fg_cache["fg"]
        if now - ts < _FG_TTL:
            return FearGreedResponse(**data)

    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=8,
            headers={"User-Agent": "seokminal-dashboard/1.0"},
        )
        resp.raise_for_status()
        raw = resp.json()["data"][0]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fear & Greed fetch failed: {exc}") from exc

    data = {
        "value": int(raw["value"]),
        "classification": raw["value_classification"],
        "timestamp": raw["timestamp"],
    }
    _fg_cache["fg"] = (now, data)
    return FearGreedResponse(**data)


def _classify_fg(v: int) -> str:
    if v <= 24: return "Extreme Fear"
    if v <= 44: return "Fear"
    if v <= 55: return "Neutral"
    if v <= 74: return "Greed"
    return "Extreme Greed"


@app.get("/macro/fear-greed/markets")
def get_fg_markets() -> dict:
    import yfinance as yf
    now = _time.time()

    # ── Crypto (Alternative.me) ─────────────────────────────────────────────
    crypto_val, crypto_cls = 50, "Neutral"
    try:
        if "fg" in _fg_cache and now - _fg_cache["fg"][0] < _FG_TTL:
            d = _fg_cache["fg"][1]
            crypto_val, crypto_cls = d["value"], d["classification"]
        else:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6,
                             headers={"User-Agent": "seokminal/1.0"})
            raw = r.json()["data"][0]
            crypto_val = int(raw["value"])
            crypto_cls = raw["value_classification"]
            _fg_cache["fg"] = (now, {"value": crypto_val, "classification": crypto_cls, "timestamp": raw["timestamp"]})
    except Exception:
        pass

    # ── US (CNN Fear & Greed) ───────────────────────────────────────────────
    us_val, us_cls = 50, "Neutral"
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            timeout=6, headers={"User-Agent": "Mozilla/5.0"}
        )
        fg = r.json()["fear_and_greed"]
        us_val = int(float(fg["score"]))
        us_cls = _classify_fg(us_val)
    except Exception:
        pass

    # ── KR (KOSPI 20d momentum proxy) ──────────────────────────────────────
    kr_val, kr_cls = 50, "Neutral"
    try:
        ks = yf.download("^KS11", period="25d", progress=False, auto_adjust=True)
        closes = ks["Close"].dropna()
        if len(closes) >= 10:
            ret_5d  = (closes.iloc[-1] / closes.iloc[-6]  - 1) * 100
            ret_20d = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) >= 21 else ret_5d
            score = 50 + ret_5d * 4 + ret_20d * 1.5
            kr_val = max(0, min(100, int(score)))
            kr_cls = _classify_fg(kr_val)
    except Exception:
        pass

    return {
        "crypto": {"value": crypto_val, "classification": crypto_cls},
        "us":     {"value": us_val,     "classification": us_cls},
        "kr":     {"value": kr_val,     "classification": kr_cls},
    }


# ── /news/* (Finnhub) ──────────────────────────────────────────────────────────

import os as _os

_FINNHUB_KEY = _os.getenv("FINNHUB_API_KEY", "")
_FINNHUB_BASE = "https://finnhub.io/api/v1"

# Cache: {key: (timestamp, list)}
_news_cache: dict[str, tuple[float, list]] = {}
_NEWS_GENERAL_TTL = 900   # 15min
_NEWS_COMPANY_TTL = 1800  # 30min


def _finnhub_key() -> str:
    if not _FINNHUB_KEY:
        raise HTTPException(status_code=503, detail="FINNHUB_API_KEY not set")
    return _FINNHUB_KEY


class QuoteResponse(BaseModel):
    symbol: str
    price: float
    ts: int  # epoch seconds


# Short-TTL cache: 여러 컴포넌트/클라가 같은 심볼 요청해도 Finnhub 호출 1회로 dedup.
# → 무료티어 60 calls/분 한도 보호. (symbol → (fetched_at, QuoteResponse))
_quote_cache: dict[str, tuple[float, "QuoteResponse"]] = {}
_QUOTE_TTL = 3.0  # seconds


@app.get("/quote", response_model=QuoteResponse)
def get_quote(symbol: str = Query(..., description="US ticker, e.g. AAPL")) -> QuoteResponse:
    """실시간 최신가 (US 주식, Finnhub). 차트 마지막 봉 라이브 갱신용. 3초 캐시."""
    sym = symbol.strip().upper().split(".")[0]
    now = _time.time()
    cached = _quote_cache.get(sym)
    if cached and now - cached[0] < _QUOTE_TTL:
        return cached[1]

    key_param = _finnhub_key()
    try:
        resp = requests.get(
            f"{_FINNHUB_BASE}/quote",
            params={"symbol": sym, "token": key_param},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Finnhub quote failed: {exc}") from exc
    price = float(data.get("c") or 0)
    if price <= 0:
        raise HTTPException(status_code=404, detail=f"no quote for {sym!r}")
    out = QuoteResponse(symbol=sym, price=price, ts=int(data.get("t") or now))
    _quote_cache[sym] = (now, out)
    return out


class NewsItem(BaseModel):
    id: int | str
    headline: str
    summary: str
    source: str
    url: str
    datetime: int
    category: str
    related: str | None = None
    image: str | None = None


@app.get("/news/market", response_model=list[NewsItem])
def get_market_news(category: str = Query("general")) -> list[NewsItem]:
    key = f"market:{category}"
    now = _time.time()
    if key in _news_cache:
        ts, data = _news_cache[key]
        if now - ts < _NEWS_GENERAL_TTL:
            return [NewsItem(**n) for n in data]

    key_param = _finnhub_key()
    try:
        resp = requests.get(
            f"{_FINNHUB_BASE}/news",
            params={"category": category, "token": key_param},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Finnhub news failed: {exc}") from exc

    items = [
        {
            "id": n.get("id", ""),
            "headline": n.get("headline", ""),
            "summary": n.get("summary", ""),
            "source": n.get("source", ""),
            "url": n.get("url", ""),
            "datetime": n.get("datetime", 0),
            "category": n.get("category", category),
            "related": n.get("related") or None,
            "image": n.get("image") or None,
        }
        for n in resp.json()[:30]
    ]
    if items:  # never cache an empty result (avoids poisoning on a transient blip)
        _news_cache[key] = (now, items)
    return [NewsItem(**n) for n in items]


@app.get("/news/company", response_model=list[NewsItem])
def get_company_news(
    ticker: str = Query(..., min_length=1),
    days: int = Query(7, ge=1, le=30),
) -> list[NewsItem]:
    cache_key = f"company:{ticker}:{days}"
    now = _time.time()
    if cache_key in _news_cache:
        ts, data = _news_cache[cache_key]
        if now - ts < _NEWS_COMPANY_TTL:
            return [NewsItem(**n) for n in data]

    key_param = _finnhub_key()
    end_dt = dt.datetime.now(dt.timezone.utc)
    start_dt = end_dt - dt.timedelta(days=days)
    try:
        resp = requests.get(
            f"{_FINNHUB_BASE}/company-news",
            params={
                "symbol": ticker.upper(),
                "from": start_dt.strftime("%Y-%m-%d"),
                "to": end_dt.strftime("%Y-%m-%d"),
                "token": key_param,
            },
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Finnhub company news failed: {exc}") from exc

    items = [
        {
            "id": n.get("id", ""),
            "headline": n.get("headline", ""),
            "summary": n.get("summary", ""),
            "source": n.get("source", ""),
            "url": n.get("url", ""),
            "datetime": n.get("datetime", 0),
            "category": n.get("category", "company"),
            "related": ticker.upper(),
            "image": n.get("image") or None,
        }
        for n in resp.json()[:20]
    ]
    _news_cache[cache_key] = (now, items)
    return [NewsItem(**n) for n in items]


# ── /screener ──────────────────────────────────────────────────────────────────

import statistics as _statistics


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-period - 1 + i] - closes[-period - 2 + i]
        (gains if diff >= 0 else losses).append(abs(diff))
    avg_g = sum(gains) / period if gains else 0
    avg_l = sum(losses) / period if losses else 0
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 2)


def _ema_val(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


class ScreenerResult(BaseModel):
    instrument_id: str
    last_price: float
    rsi14: float | None
    ema12: float | None
    ema26: float | None
    ema_signal: str  # "bullish_cross" | "bearish_cross" | "above" | "below" | "neutral"
    change_pct: float | None


@app.get("/screener", response_model=list[ScreenerResult])
def run_screener(
    instruments: str = Query(..., description="Comma-separated instrument IDs"),
    rsi_min: float | None = Query(None),
    rsi_max: float | None = Query(None),
    ema_signal: str | None = Query(None, description="bullish_cross|bearish_cross|above|below"),
    days: int = Query(60, ge=20, le=365),
) -> list[ScreenerResult]:
    from catalog.client import CatalogClient  # type: ignore

    ids = [s.strip() for s in instruments.split(",") if s.strip()][:30]
    client = CatalogClient()
    results: list[ScreenerResult] = []

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=days)

    for inst in ids:
        try:
            bars = client.get_bars(inst, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            if not bars or len(bars) < 15:
                continue
            closes = [b["close"] for b in bars]
            last = closes[-1]
            prev = closes[-2] if len(closes) >= 2 else last
            rsi = _compute_rsi(closes)
            e12 = _ema_val(closes, 12)
            e26 = _ema_val(closes, 26)
            e12_prev = _ema_val(closes[:-1], 12)
            e26_prev = _ema_val(closes[:-1], 26)

            sig = "neutral"
            if e12 and e26:
                if e12_prev and e26_prev:
                    if e12_prev <= e26_prev and e12 > e26:
                        sig = "bullish_cross"
                    elif e12_prev >= e26_prev and e12 < e26:
                        sig = "bearish_cross"
                    elif e12 > e26:
                        sig = "above"
                    else:
                        sig = "below"

            # apply filters
            if rsi_min is not None and (rsi is None or rsi < rsi_min):
                continue
            if rsi_max is not None and (rsi is None or rsi > rsi_max):
                continue
            if ema_signal and sig != ema_signal:
                continue

            results.append(ScreenerResult(
                instrument_id=inst,
                last_price=round(last, 2),
                rsi14=rsi,
                ema12=round(e12, 2) if e12 else None,
                ema26=round(e26, 2) if e26 else None,
                ema_signal=sig,
                change_pct=round((last - prev) / prev * 100, 2) if prev else None,
            ))
        except Exception:
            continue

    return results


# ── /hl/trade (Hyperliquid 거래) ───────────────────────────────────────────────

class HLOrderRequest(BaseModel):
    coin: str
    is_buy: bool
    size: float = Field(gt=0)
    order_type: str = "market"
    limit_px: float | None = None
    reduce_only: bool = False
    slippage: float = 0.05
    paper: bool = False


class HLCancelRequest(BaseModel):
    coin: str
    oid: int
    paper: bool = False


class HLCloseRequest(BaseModel):
    coin: str
    size: float | None = None
    slippage: float = 0.05
    paper: bool = False


def _hl_trader():
    try:
        from hyperliquid.trader import get_positions, place_order, cancel_order, close_position
        return get_positions, place_order, cancel_order, close_position
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Hyperliquid trader not available: {e}") from e


@app.get("/hl/positions")
def hl_positions(paper: bool = False) -> dict:
    get_positions, *_ = _hl_trader()
    try:
        return get_positions(paper=paper)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HL API error: {e}") from e


@app.post("/hl/order")
def hl_place_order(req: HLOrderRequest) -> dict:
    _, place_order, *_ = _hl_trader()
    if req.size <= 0:
        raise HTTPException(status_code=400, detail="size must be > 0")
    if req.order_type not in ("market", "limit"):
        raise HTTPException(status_code=400, detail="order_type must be 'market' or 'limit'")
    if req.order_type == "limit" and req.limit_px is None:
        raise HTTPException(status_code=400, detail="limit_px required for limit order")
    if req.slippage < 0 or req.slippage > 0.5:
        raise HTTPException(status_code=400, detail="slippage must be 0~0.5")
    # reduce_only orders unwind exposure — exempt from the position cap path.
    if not req.reduce_only:
        _check_risk(
            side="BUY" if req.is_buy else "SELL",
            quantity=req.size,
            price_estimate=req.limit_px,
        )
    try:
        result = place_order(
            coin=req.coin,
            is_buy=req.is_buy,
            size=req.size,
            order_type=req.order_type,
            limit_px=req.limit_px,
            reduce_only=req.reduce_only,
            slippage=req.slippage,
            paper=req.paper,
        )
        record_order(venue="HL", request=req.model_dump(), result={"result": result}, status="submitted")
        return {"status": "ok", "paper": req.paper, "result": result}
    except ValueError as e:
        record_order(venue="HL", request=req.model_dump(), result=None, status="error")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_order(venue="HL", request=req.model_dump(), result=None, status="error")
        raise HTTPException(status_code=502, detail=f"HL order failed: {e}") from e


@app.post("/hl/order/cancel")
def hl_cancel_order(req: HLCancelRequest) -> dict:
    _, _, cancel_order, _ = _hl_trader()
    try:
        result = cancel_order(coin=req.coin, oid=req.oid, paper=req.paper)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HL cancel failed: {e}") from e


@app.post("/hl/order/close")
def hl_close_position(req: HLCloseRequest) -> dict:
    _, _, _, close_position = _hl_trader()
    try:
        result = close_position(coin=req.coin, size=req.size, slippage=req.slippage, paper=req.paper)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HL close failed: {e}") from e


class HLLeverageRequest(BaseModel):
    coin: str
    leverage: int = Field(ge=1, le=50)
    is_cross: bool = True
    paper: bool = False


@app.post("/hl/leverage")
def hl_set_leverage(req: HLLeverageRequest) -> dict:
    """Set leverage for a coin before sizing a leveraged day-trade position."""
    try:
        from hyperliquid.trader import set_leverage
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"HL trader unavailable: {e}") from e
    try:
        result = set_leverage(req.coin, req.leverage, req.is_cross, req.paper)
        return {"status": "ok", "coin": req.coin.upper(), "leverage": req.leverage, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HL set leverage failed: {e}") from e


@app.get("/hl/intraday/scores")
def hl_intraday_scores(coins: str, paper: bool = True) -> dict:
    """Intraday (crypto 24/7) scoring for HL perps. ``coins`` comma-separated.

    Pulls HL 5-min candles and runs the crypto-mode intraday engine
    (rolling VWAP, no session/ToD reset). Default paper=True (testnet).
    """
    try:
        from hyperliquid.trader import get_candles
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"HL trader unavailable: {e}") from e
    from api_server import intraday_score as _iz

    out = {}
    for coin in [c.strip().upper() for c in coins.split(",") if c.strip()]:
        try:
            bars = get_candles(coin, interval="5m", lookback_min=1440, paper=paper)
            res = _iz.score_intraday(bars, crypto=True)
        except Exception as e:
            res = {"direction": "FLAT", "score": 0, "signal": "AVOID", "error": str(e)}
        res["symbol"] = coin
        out[coin] = res
    return {"scores": out}

# ── Quant Advanced Routes (Group 3) ──────────────────────────────────────────
from api_server.router_quant3 import router as quant3_router
app.include_router(quant3_router)


# ── Quant Advanced Routes (Group 2) ──────────────────────────────────────────
from api_server.router_quant2 import router as quant2_router
app.include_router(quant2_router)


# ── Quant Advanced Routes (Group 1) ──────────────────────────────────────────
from api_server.router_quant1 import router as quant1_router
app.include_router(quant1_router)


# ── Alpaca Autopilot ──────────────────────────────────────────────────────────
from api_server.router_autopilot import router as autopilot_router, agents_router
app.include_router(autopilot_router)
app.include_router(agents_router)

# ── 리스크 (킬스위치 + drawdown 자동차단) ─────────────────────────────────────────
from api_server.risk_state import router as risk_router
app.include_router(risk_router)

# ── DART 기업행위 자동매매 봇 (서버측, 브라우저 무관) ──────────────────────────────
from api_server.dart_autobot import router as dart_bot_router, start_loop as _dart_bot_start
app.include_router(dart_bot_router)

# ── VRP(변동성 리스크 프리미엄) 아이언 콘도어 옵션 봇 (서버측) ─────────────────────
from api_server.vrp_bot import router as vrp_bot_router, start_loop as _vrp_bot_start
app.include_router(vrp_bot_router)

# ── Polymarket 페이퍼 다각화 배스킷 봇 (서버측) ───────────────────────────────────
from api_server.polymarket_bot import router as polymarket_bot_router, start_loop as _polymarket_bot_start
app.include_router(polymarket_bot_router)

# ── Strategy Validation Terminal (research 산출물) ────────────────────────────────
from api_server.research_api import router as research_router
app.include_router(research_router)

# ── AI LAB (자율 리서치 루프: 자체생각→검토→집행→학습) ─────────────────────────────
from api_server.lab_api import router as lab_router
app.include_router(lab_router)

# ── Living Knowledge Graph (AI 인프라 공급망 그래프) ────────────────────────────
from api_server.graph_api import router as graph_router
app.include_router(graph_router)

# ── ICT 프리미티브 자유조합 백테스트(탐색용) ──────────────────────────────────────
from api_server.router_ict import router as ict_router
app.include_router(ict_router)

from api_server.router_orderflow import router as orderflow_router
app.include_router(orderflow_router)


@app.on_event("startup")
async def _start_dart_bot() -> None:
    _dart_bot_start()
    _vrp_bot_start()
    _polymarket_bot_start()
    # Jarvis 부트(시드 + paper_candidate 자동 forward 배선) + 서버사이드 리서치 서비스(D).
    try:
        import jarvis
        jarvis.boot()
        from research.lab.service import SERVICE
        SERVICE.start()
    except Exception:  # noqa: BLE001
        pass
    # Living Knowledge Graph 6h 자동 업데이트 스케줄러.
    # 토요일·일요일 낮은 미국/한국 증시 휴장이라 스킵. 단 일요일 저녁(KST)은
    # 월요일 개장 전 주말 사이 이벤트를 한 번 훑어야 하므로 실행.
    import asyncio
    async def _lkg_scheduler() -> None:
        import os as _os
        from datetime import datetime, timedelta, timezone
        from api_server.graph_api import run_ai_update
        KST = timezone(timedelta(hours=9))
        await asyncio.sleep(60)  # 서버 완전 기동 후 1분 대기
        while True:
            try:
                now = datetime.now(KST)
                wd = now.weekday()  # 0=월 ... 5=토 6=일
                skip_weekend = wd == 5 or (wd == 6 and now.hour < 18)
                if not skip_weekend:
                    key = _os.environ.get("FINNHUB_API_KEY", "")
                    if key:
                        run_ai_update(key)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(6 * 3600)  # 6시간 주기
    asyncio.create_task(_lkg_scheduler())


# ── Market Overview ───────────────────────────────────────────────────────────
_FX_CACHE: dict = {}
_FX_TTL = 60

@app.get("/forex/overview")
def forex_overview() -> dict:
    import yfinance as yf
    now = _time.time()
    if "d" in _FX_CACHE and now - _FX_CACHE["d"][0] < _FX_TTL:
        return _FX_CACHE["d"][1]

    PAIRS = {
        "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X",
        "USD/CHF": "USDCHF=X", "AUD/USD": "AUDUSD=X", "NZD/USD": "NZDUSD=X",
        "USD/CAD": "USDCAD=X", "USD/KRW": "USDKRW=X", "USD/CNY": "USDCNY=X",
        "EUR/GBP": "EURGBP=X", "EUR/JPY": "EURJPY=X", "GBP/JPY": "GBPJPY=X",
    }
    result = {}
    for pair, sym in PAIRS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                result[pair] = {"rate": None, "change_pct": None, "change_5d": None}
                continue
            rate = float(closes.iloc[-1])
            chg1d = (rate - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100
            chg5d = (rate - float(closes.iloc[0]))  / float(closes.iloc[0])  * 100
            result[pair] = {
                "rate":       round(rate, 4),
                "change_pct": round(chg1d, 3),
                "change_5d":  round(chg5d, 3),
            }
        except Exception:
            result[pair] = {"rate": None, "change_pct": None, "change_5d": None}

    _FX_CACHE["d"] = (now, result)
    return result


@app.get("/market-overview")
def market_overview() -> dict:
    import yfinance as yf  # type: ignore
    TICKERS = {
        "sp500":   "^GSPC",
        "nasdaq":  "^IXIC",
        "usdkrw":  "USDKRW=X",
        "btcusd":  "BTC-USD",
        "vix":     "^VIX",
        "gold":    "GC=F",
    }
    result = {}
    for key, symbol in TICKERS.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d", interval="1d")
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                last_close = float(hist["Close"].iloc[-1])
                change_pct = (last_close - prev_close) / prev_close * 100
            elif len(hist) == 1:
                last_close = float(hist["Close"].iloc[-1])
                change_pct = 0.0
            else:
                result[key] = {"value": None, "change_pct": None}
                continue
            result[key] = {"value": round(last_close, 4), "change_pct": round(change_pct, 2)}
        except Exception:
            result[key] = {"value": None, "change_pct": None}
    return result


# ── /claude/usage ──────────────────────────────────────────────────────────────

_usage_cache: dict = {}
_USAGE_TTL = 300  # 5 min

@app.get("/claude/usage")
def get_claude_usage() -> dict:
    import glob, json as _json
    from datetime import datetime, timedelta, timezone

    now = _time.time()
    if "u" in _usage_cache and now - _usage_cache["u"][0] < _USAGE_TTL:
        return _usage_cache["u"][1]

    home = _os.path.expanduser("~")
    projects_dir = _os.path.join(home, ".claude", "projects")
    utc_now = datetime.now(timezone.utc)
    today_str = utc_now.strftime("%Y-%m-%d")
    week_ago = utc_now - timedelta(days=7)

    daily_in = daily_out = 0
    weekly_in = weekly_out = 0

    for jsonl_file in glob.glob(_os.path.join(projects_dir, "**", "*.jsonl"), recursive=True):
        try:
            with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        obj = _json.loads(line)
                        ts = obj.get("timestamp", "")
                        if not ts:
                            continue
                        msg = obj.get("message", {})
                        if not isinstance(msg, dict):
                            continue
                        usage = msg.get("usage", {})
                        if not usage:
                            continue
                        inp = int(usage.get("input_tokens", 0) or 0)
                        out = int(usage.get("output_tokens", 0) or 0)
                        if inp == 0 and out == 0:
                            continue
                        if ts[:10] == today_str:
                            daily_in += inp
                            daily_out += out
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if dt >= week_ago:
                            weekly_in += inp
                            weekly_out += out
                    except Exception:
                        pass
        except Exception:
            pass

    result = {
        "daily":  {"input": daily_in,  "output": daily_out,  "total": daily_in  + daily_out},
        "weekly": {"input": weekly_in, "output": weekly_out, "total": weekly_in + weekly_out},
        "daily_cap":  2_000_000,
        "weekly_cap": 25_000_000,
    }
    _usage_cache["u"] = (now, result)
    return result


# ── Groq Summary ──────────────────────────────────────────────────────────────

class GroqSummarizeRequest(BaseModel):
    content: str
    mode: str = "news"  # "news" | "calendar"


class StockPick(BaseModel):
    symbol: str
    direction: str  # "up" | "down" | "neutral"


class GroqSummarizeResponse(BaseModel):
    summary: str
    picks: list[StockPick] = []


@app.post("/groq/summarize", response_model=GroqSummarizeResponse)
def groq_summarize(body: GroqSummarizeRequest) -> GroqSummarizeResponse:
    import re
    from openai import OpenAI

    picks_instruction = """
마지막 줄에 반드시 아래 형식으로 관련 미국 주식 티커 추가 (언급된 종목만, 없으면 생략):
STOCKS: NVDA↑ AAPL↓ MSFT↑
규칙: 티커↑(상승전망) 티커↓(하락전망) — 최대 5개, 미국 상장 종목만"""

    if body.mode == "calendar":
        system = """당신은 매크로 트레이딩 전략가입니다. 이번 주 경제지표 일정을 보고 투자 전략을 한국어로 작성하세요.

형식 규칙:
- 마크다운 헤더(#, ##) 절대 금지
- **볼드** 절대 금지
- 각 항목은 "· " 으로 시작
- 4~6개 항목, 각 항목 1~2문장
- 반드시 포함: 상승 전망 자산, 하락 전망 자산, 주목 섹터, 핵심 리스크

예시:
· 이번 주 미국 CPI 발표 예정으로 인플레이션 둔화 시 나스닥 상승 전망.
· 달러 약세 가능성으로 금, 신흥국 통화가 수혜를 받을 전망.
· 에너지 섹터는 공급 우려로 강세 흐름 유지될 것으로 보임.
· 영국 GDP 발표 부진 시 파운드화 하락 리스크 주의.""" + picks_instruction
    else:
        system = """당신은 매크로 트레이딩 전략가입니다. 뉴스 헤드라인과 요약을 보고 투자 전략을 한국어로 작성하세요. 제목만으로 속단하지 말고 제공된 요약 내용을 근거로 판단하세요.

형식 규칙:
- 마크다운 헤더(#, ##) 절대 금지
- **볼드** 절대 금지
- 각 항목은 "· " 으로 시작
- 4~6개 항목, 각 항목 1~2문장
- 반드시 포함: 오를 전망 자산/섹터, 떨어질 전망 자산/섹터, 핵심 리스크, 단기 전략

예시:
· 연준 금리 동결로 성장주 중심 나스닥이 단기 상승 전망.
· 유가 하락세로 에너지 섹터는 약세, 항공·물류 섹터는 수혜 기대.
· 미-이란 긴장 완화 시 위험자산 선호 심리 강화될 전망.
· 기술 섹터 AI 투자 확대로 반도체 관련주 강세 흐름 지속 예상.""" + picks_instruction

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )
    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=500,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": body.content[:6000]},
        ],
    )
    raw = resp.choices[0].message.content.strip()

    # Parse STOCKS: line and remove from summary
    lines = raw.split("\n")
    stocks_line = next((l for l in lines if l.strip().startswith("STOCKS:")), None)
    clean_lines = [l for l in lines if not l.strip().startswith("STOCKS:")]
    summary = "\n".join(clean_lines).strip()

    picks: list[StockPick] = []
    if stocks_line:
        for m in re.finditer(r"([A-Z]{1,5})(↑|↓)", stocks_line):
            sym, arrow = m.group(1), m.group(2)
            picks.append(StockPick(symbol=sym, direction="up" if arrow == "↑" else "down"))

    return GroqSummarizeResponse(summary=summary, picks=picks)
