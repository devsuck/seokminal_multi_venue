"""페어(스프레드) 백테스트 — z-score 신호로 스프레드 매매, 거래비용 반영.

시장중립 stat-arb: buy_spread=롱A/숏(hedge×B), sell_spread=반대, exit=청산.
스프레드 = A − hedge×B − intercept 를 합성자산으로 보고 PnL 계산."""
from __future__ import annotations

import math
import statistics as _st


def backtest_pairs(
    prices_a: list[float],
    prices_b: list[float],
    hedge_ratio: float,
    spread: list[float],
    signals: list[str],
    cost_bps: float = 5.0,
) -> dict:
    n = min(len(spread), len(signals), len(prices_a), len(prices_b))
    if n < 5:
        return {"error": "데이터 부족"}

    # 스프레드 1단위 명목가치(진입 시점 근사) — 비용 산정용
    def notional(i: int) -> float:
        return abs(prices_a[i]) + abs(hedge_ratio) * abs(prices_b[i])

    base_notional = sum(notional(i) for i in range(n)) / n or 1.0
    cost_rate = cost_bps / 10_000.0

    position = 0            # +1 롱스프레드 / -1 숏스프레드 / 0 청산
    entry_spread = 0.0
    daily_pnl: list[float] = []
    trades: list[float] = []
    cum = 0.0
    peak = 0.0
    mdd = 0.0

    for i in range(n):
        # 바 PnL = 직전 포지션 × 스프레드 변화
        if i > 0 and position != 0:
            pnl = position * (spread[i] - spread[i - 1])
        else:
            pnl = 0.0

        sig = signals[i]
        target = position
        if sig == "buy_spread":
            target = 1
        elif sig == "sell_spread":
            target = -1
        elif sig == "exit":
            target = 0

        if target != position:
            # 포지션 변경 → 거래비용(양쪽 명목) + 왕복 손익 기록
            trade_cost = notional(i) * cost_rate * (abs(target - position))
            pnl -= trade_cost
            if position != 0:
                trades.append((spread[i] - entry_spread) * position)
            if target != 0:
                entry_spread = spread[i]
            position = target

        cum += pnl
        peak = max(peak, cum)
        if peak > 0:
            mdd = min(mdd, (cum - peak) / peak)
        daily_pnl.append(pnl)

    # 지표
    total_return_pct = round(cum / base_notional * 100, 2)
    sharpe = None
    rets = [p / base_notional for p in daily_pnl]
    if len(rets) > 1 and _st.pstdev(rets) > 1e-12:
        sharpe = round(_st.mean(rets) / _st.pstdev(rets) * math.sqrt(252), 2)
    wins = [t for t in trades if t > 0]
    win_rate = round(len(wins) / len(trades), 3) if trades else None

    return {
        "total_return_pct": total_return_pct,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": round(mdd * 100, 2),
        "num_trades": len(trades),
        "win_rate": win_rate,
        "cost_bps": cost_bps,
    }
