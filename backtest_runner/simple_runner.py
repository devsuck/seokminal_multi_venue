"""Pure-Python MACD and RSI backtester. Produces the same dict format as run_backtest."""
from __future__ import annotations

import math
import statistics as _st


# ── EMA helper ────────────────────────────────────────────────────────────────

def _ema_series(values: list[float], period: int) -> list[float | None]:
    """Return EMA for each index; None for warmup period (index < period - 1)."""
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    ema = sum(values[:period]) / period
    result[period - 1] = ema
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        result[i] = ema
    return result


# ── MACD signals ──────────────────────────────────────────────────────────────

def _macd_signals(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> list[str]:
    """Return "BUY", "SELL", or "HOLD" per bar index based on MACD crossover."""
    fast_emas = _ema_series(closes, fast)
    slow_emas = _ema_series(closes, slow)

    macd_line: list[float | None] = [
        (fast_emas[i] - slow_emas[i])  # type: ignore[operator]
        if fast_emas[i] is not None and slow_emas[i] is not None
        else None
        for i in range(len(closes))
    ]

    # Extract non-None MACD values to compute signal line EMA
    valid: list[tuple[int, float]] = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: list[float | None] = [None] * len(closes)
    if len(valid) >= signal_period:
        raw_vals = [v for _, v in valid]
        sig_emas = _ema_series(raw_vals, signal_period)
        for j, (orig_i, _) in enumerate(valid):
            if sig_emas[j] is not None:
                signal_line[orig_i] = sig_emas[j]

    signals = ["HOLD"] * len(closes)
    for i in range(1, len(closes)):
        m = macd_line[i]
        s = signal_line[i]
        m_prev = macd_line[i - 1]
        s_prev = signal_line[i - 1]
        if None in (m, s, m_prev, s_prev):
            continue
        # Crossover: MACD crosses above signal → BUY; crosses below → SELL
        if m_prev <= s_prev and m > s:  # type: ignore[operator]
            signals[i] = "BUY"
        elif m_prev >= s_prev and m < s:  # type: ignore[operator]
            signals[i] = "SELL"
    return signals


# ── RSI signals ───────────────────────────────────────────────────────────────

def _rsi_series(closes: list[float], period: int) -> list[float | None]:
    """Return RSI value per bar index using Wilder's smoothing."""
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in diffs]
    losses = [max(-d, 0.0) for d in diffs]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi_val(ag: float, al: float) -> float:
        return 100.0 if al == 0.0 else 100.0 - 100.0 / (1 + ag / al)

    result[period] = _rsi_val(avg_gain, avg_loss)

    for i in range(period, len(diffs)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi_val(avg_gain, avg_loss)

    return result


def _rsi_signals(
    closes: list[float],
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> list[str]:
    """Return "BUY" when RSI crosses up from oversold; "SELL" when crosses down from overbought."""
    rsi = _rsi_series(closes, period)
    signals = ["HOLD"] * len(closes)
    for i in range(1, len(closes)):
        r = rsi[i]
        r_prev = rsi[i - 1]
        if r is None or r_prev is None:
            continue
        if r_prev <= oversold and r > oversold:
            signals[i] = "BUY"
        elif r_prev >= overbought and r < overbought:
            signals[i] = "SELL"
    return signals


# ── EMA Cross signals ─────────────────────────────────────────────────────────

def _ema_signals(closes: list[float], fast: int, slow: int) -> list[str]:
    """BUY on golden cross (fast crosses above slow), SELL on death cross, else HOLD."""
    fast_ema = _ema_series(closes, fast)
    slow_ema = _ema_series(closes, slow)
    signals: list[str] = []
    for i in range(len(closes)):
        f = fast_ema[i]
        s = slow_ema[i]
        if f is None or s is None:
            signals.append("HOLD")
            continue
        if i == 0:
            signals.append("HOLD")
            continue
        pf = fast_ema[i - 1]
        ps = slow_ema[i - 1]
        if pf is None or ps is None:
            signals.append("HOLD")
        elif f > s and pf <= ps:
            signals.append("BUY")
        elif f < s and pf >= ps:
            signals.append("SELL")
        else:
            signals.append("HOLD")
    return signals


# ── Trade simulation ──────────────────────────────────────────────────────────

def _simulate_trades(
    closes: list[float],
    ts_events: list[int],
    signals: list[str],
    trade_size: int,
) -> list[dict]:
    """Simulate long/short trades based on BUY/SELL signals. Returns closed trade dicts."""
    position = 0  # 0=flat, 1=long, -1=short
    entry_price: float | None = None
    entry_ts_ns: int | None = None
    trades: list[dict] = []

    for price, ts, signal in zip(closes, ts_events, signals):
        if signal == "BUY" and position <= 0:
            if position < 0 and entry_price is not None:
                pnl = (entry_price - price) * trade_size
                trades.append({
                    "entry_ts_ns": entry_ts_ns,
                    "exit_ts_ns": ts,
                    "side": "SHORT",
                    "entry_price": entry_price,
                    "exit_price": price,
                    "qty": float(trade_size),
                    "pnl": round(pnl, 6),
                })
            entry_price = price
            entry_ts_ns = ts
            position = 1
        elif signal == "SELL" and position >= 0:
            if position > 0 and entry_price is not None:
                pnl = (price - entry_price) * trade_size
                trades.append({
                    "entry_ts_ns": entry_ts_ns,
                    "exit_ts_ns": ts,
                    "side": "LONG",
                    "entry_price": entry_price,
                    "exit_price": price,
                    "qty": float(trade_size),
                    "pnl": round(pnl, 6),
                })
            # Always open SHORT unconditionally
            entry_price = price
            entry_ts_ns = ts
            position = -1

    # Close any open position at last bar
    if position != 0 and entry_price is not None and closes:
        last_price = closes[-1]
        last_ts = ts_events[-1]
        pnl = (last_price - entry_price) * trade_size if position > 0 else (entry_price - last_price) * trade_size
        trades.append({
            "entry_ts_ns": entry_ts_ns,
            "exit_ts_ns": last_ts,
            "side": "LONG" if position > 0 else "SHORT",
            "entry_price": entry_price,
            "exit_price": last_price,
            "qty": float(trade_size),
            "pnl": round(pnl, 6),
        })

    return trades


# ── Stats ─────────────────────────────────────────────────────────────────────

def _compute_stats(closes: list[float], ts_events: list[int], trades: list[dict]) -> dict:
    """Compute performance stats from trades and bar returns."""
    bar_returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]

    sharpe: float | None = None
    sortino: float | None = None
    volatility: float | None = None
    if len(bar_returns) >= 2:
        vol_daily = _st.stdev(bar_returns)
        volatility = vol_daily * math.sqrt(252)
        mean_r = _st.mean(bar_returns)
        if vol_daily > 1e-10:
            sharpe = mean_r / vol_daily * math.sqrt(252)
        downside = [r for r in bar_returns if r < 0]
        if len(downside) >= 2:
            dd_std = _st.stdev(downside)
            if dd_std > 1e-10:
                sortino = mean_r / dd_std * math.sqrt(252)

    # Max drawdown from cumulative PnL series
    max_drawdown: float | None = None
    if trades:
        cum = 0.0
        peak = 0.0
        worst = 0.0
        for t in trades:
            cum += t["pnl"] or 0.0
            if cum > peak:
                peak = cum
            dd = (cum - peak) / peak if peak > 0 else 0.0
            if dd < worst:
                worst = dd
        max_drawdown = worst if worst != 0.0 else None

    pnls = [t["pnl"] for t in trades if t["pnl"] is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls) if pnls else None
    win_rate = len(wins) / len(pnls) if pnls else None
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    pl_ratio = (avg_win / abs(avg_loss)) if (avg_win and avg_loss) else None

    # total_pnl_pct relative to first bar price (proxy for starting capital unit)
    total_pnl_pct: float | None = None
    if total_pnl is not None and closes:
        total_pnl_pct = total_pnl / closes[0] if closes[0] > 0 else None

    return {
        "bar_count": len(closes),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "win_rate": win_rate,
        "profit_loss_ratio": pl_ratio,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "trades": trades,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def run_simple_backtest(bars: list, strategy: str, params: dict) -> dict:
    """Run MACD, RSI, or EMA Cross backtest on the given bars. Returns same dict format as run_backtest."""
    closes = [float(b.close) for b in bars]
    ts_events = [b.ts_event for b in bars]
    trade_size = int(params.get("trade_size", 10))

    if strategy == "macd":
        signals = _macd_signals(
            closes,
            fast=int(params.get("fast", 12)),
            slow=int(params.get("slow", 26)),
            signal_period=int(params.get("signal_period", 9)),
        )
    elif strategy == "rsi":
        signals = _rsi_signals(
            closes,
            period=int(params.get("period", 14)),
            oversold=float(params.get("oversold", 30)),
            overbought=float(params.get("overbought", 70)),
        )
    elif strategy == "ema_cross":
        signals = _ema_signals(
            closes,
            fast=int(params.get("fast", 12)),
            slow=int(params.get("slow", 26)),
        )
    else:
        raise ValueError(f"unknown strategy {strategy!r}")

    trades = _simulate_trades(closes, ts_events, signals, trade_size)
    return _compute_stats(closes, ts_events, trades)
