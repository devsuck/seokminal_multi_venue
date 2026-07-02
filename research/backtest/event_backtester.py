"""이벤트 기반 롱온리 백테스터 — 신호 진입 후 ATR스탑/R타겟/타임스탑/VWAP이탈로 청산.

signal flip(BUY/SELL) 방식과 달리 진입마다 명시적 exit 규칙 적용(ORB류에 적합).
한 번에 한 포지션(피라미딩 없음). 비용 = (진입+청산)×size×bps/1e4 (왕복)."""
from __future__ import annotations


def _cost(entry: float, exit_: float, size: float, cost_bps: float) -> float:
    return (abs(entry) + abs(exit_)) * size * cost_bps / 10_000.0


def run_event_backtest(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    entry_signals: list[bool],
    atr_abs: list[float | None],
    trade_size: float = 10.0,
    cost_bps: float = 0.0,
    stop_atr: float = 1.0,
    target_atr: float = 2.0,
    time_stop_bars: int = 8,
    vwap: list[float | None] | None = None,
) -> list[dict]:
    """롱온리 이벤트 백테스트. 반환: [{entry_idx,exit_idx,side,entry_price,exit_price,pnl,exit_reason}]."""
    n = len(closes)
    trades: list[dict] = []
    i = 0
    while i < n:
        if not entry_signals[i] or atr_abs[i] is None or atr_abs[i] <= 0:
            i += 1
            continue
        entry_px = closes[i]
        a = atr_abs[i]
        stop = entry_px - stop_atr * a
        target = entry_px + target_atr * a
        exit_idx = min(i + time_stop_bars, n - 1)
        exit_px = closes[exit_idx]
        reason = "time_stop"
        for j in range(i + 1, min(i + time_stop_bars, n - 1) + 1):
            if lows[j] <= stop:          # 스탑 우선(보수적: 같은 봉 동시터치 시 손절)
                exit_idx, exit_px, reason = j, stop, "stop"
                break
            if highs[j] >= target:
                exit_idx, exit_px, reason = j, target, "target"
                break
            if vwap is not None and vwap[j] is not None and closes[j] < vwap[j]:
                exit_idx, exit_px, reason = j, closes[j], "vwap_loss"
                break
        pnl = (exit_px - entry_px) * trade_size - _cost(entry_px, exit_px, trade_size, cost_bps)
        trades.append({
            "entry_idx": i, "exit_idx": exit_idx, "side": "LONG",
            "entry_price": entry_px, "exit_price": exit_px,
            "pnl": round(pnl, 6), "exit_reason": reason,
        })
        i = exit_idx + 1  # 청산 후부터 재진입 탐색(중첩 금지)
    return trades
