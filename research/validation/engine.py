"""인덱스 기반 롱/숏 체결 시뮬레이터 (리서치 자체 완결).

simple_runner._simulate_trades와 규약 동일(왕복 비용 = 진입+청산 2회 차감)하되
bar 인덱스로 동작 → holding(봉수) 측정·랜덤 진입 생성에 재사용."""
from __future__ import annotations


def _cost(entry: float, exit_: float, trade_size: float, cost_bps: float) -> float:
    return (abs(entry) + abs(exit_)) * trade_size * cost_bps / 10_000.0


def simulate_long_short(
    closes: list[float],
    signals: list[str],
    trade_size: float = 10.0,
    cost_bps: float = 0.0,
) -> list[dict]:
    """BUY/SELL 신호로 롱/숏 왕복 매매. 마지막 봉에서 잔여 청산.
    반환: [{entry_idx, exit_idx, side, entry_price, exit_price, pnl}]."""
    position = 0
    entry_px: float | None = None
    entry_idx: int | None = None
    trades: list[dict] = []
    n = len(closes)

    for i in range(n):
        sig = signals[i]
        px = closes[i]
        if sig == "BUY" and position <= 0:
            if position < 0 and entry_px is not None:
                pnl = (entry_px - px) * trade_size - _cost(entry_px, px, trade_size, cost_bps)
                trades.append({"entry_idx": entry_idx, "exit_idx": i, "side": "SHORT",
                               "entry_price": entry_px, "exit_price": px, "pnl": round(pnl, 6)})
            entry_px, entry_idx, position = px, i, 1
        elif sig == "SELL" and position >= 0:
            if position > 0 and entry_px is not None:
                pnl = (px - entry_px) * trade_size - _cost(entry_px, px, trade_size, cost_bps)
                trades.append({"entry_idx": entry_idx, "exit_idx": i, "side": "LONG",
                               "entry_price": entry_px, "exit_price": px, "pnl": round(pnl, 6)})
            entry_px, entry_idx, position = px, i, -1

    if position != 0 and entry_px is not None and n:
        last = closes[-1]
        gross = (last - entry_px) * trade_size if position > 0 else (entry_px - last) * trade_size
        pnl = gross - _cost(entry_px, last, trade_size, cost_bps)
        trades.append({"entry_idx": entry_idx, "exit_idx": n - 1,
                       "side": "LONG" if position > 0 else "SHORT",
                       "entry_price": entry_px, "exit_price": last, "pnl": round(pnl, 6)})
    return trades


def simulate_fixed_hold_longs(
    closes: list[float],
    entries: list[int],
    holds: list[int],
    trade_size: float = 10.0,
    cost_bps: float = 0.0,
) -> list[dict]:
    """지정 진입 인덱스 + 보유봉수로 롱온리 체결(랜덤 베이스라인용).
    exit_idx = min(entry+hold, n-1)."""
    n = len(closes)
    trades: list[dict] = []
    for e, h in zip(entries, holds):
        if e < 0 or e >= n:
            continue
        x = min(e + max(1, h), n - 1)
        entry_px, exit_px = closes[e], closes[x]
        pnl = (exit_px - entry_px) * trade_size - _cost(entry_px, exit_px, trade_size, cost_bps)
        trades.append({"entry_idx": e, "exit_idx": x, "side": "LONG",
                       "entry_price": entry_px, "exit_price": exit_px, "pnl": round(pnl, 6)})
    return trades
