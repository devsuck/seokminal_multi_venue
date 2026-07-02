"""거래 기반 성과 지표 (기존 simple_runner의 Sharpe는 종목 봉수익률로 계산돼
전략 비교에 부적합 → 여기선 거래 PnL 기반으로 정확히 계산)."""
from __future__ import annotations

import math
import statistics as _st

MIN_TRADES = 30  # 이하면 통계적으로 underpowered


def trade_metrics(trades: list[dict], min_trades: int = MIN_TRADES) -> dict:
    """거래 리스트 → 지표. per_trade_sharpe = 평균/표준편차 (거래단위, 미연율화)."""
    pnls = [t["pnl"] for t in trades if t.get("pnl") is not None]
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total = sum(pnls) if pnls else 0.0
    expectancy = (total / n) if n else 0.0
    win_rate = (len(wins) / n) if n else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)

    per_trade_sharpe: float | None = None
    if n >= 2:
        sd = _st.stdev(pnls)
        if sd > 1e-12:
            per_trade_sharpe = _st.mean(pnls) / sd

    # max drawdown (누적 PnL 기준)
    max_dd = 0.0
    cum = peak = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        if peak > 0:
            max_dd = min(max_dd, (cum - peak) / peak)

    return {
        "num_trades": n,
        "total_pnl": round(total, 6),
        "expectancy": round(expectancy, 6),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "profit_factor": (round(profit_factor, 4) if math.isfinite(profit_factor) else None),
        "per_trade_sharpe": (round(per_trade_sharpe, 4) if per_trade_sharpe is not None else None),
        "max_drawdown": round(max_dd, 4) if max_dd != 0.0 else None,
        "underpowered": n < min_trades,
    }
