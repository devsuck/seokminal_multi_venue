"""Deterministic day-trading decision rules (no LLM).

Day-trading is mechanical: the intraday engine already produces direction,
conviction and ATR-based entry/stop/target, so a rules layer — not an LLM —
drives orders. This keeps every cycle fast, consistent, and free of token
cost. Pure functions over the scores + current positions.

Entry: highest-conviction actionable signal at/above the threshold. On equity
(US) only longs are actionable (no easy shorting); on HL (perps) both sides.
Exit: close a held position when its signal flips against it or degrades to
AVOID/WATCH.
"""
from __future__ import annotations

_ACTIONABLE_LONG = {"STRONG_BUY", "BUY"}
_ACTIONABLE_SHORT = {"STRONG_SELL", "SELL"}


def decide_entry(scores: dict[str, dict], threshold: float, allow_short: bool) -> dict | None:
    """Pick the single best entry from a {symbol: score_result} map, or None.

    Only signals at/above ``threshold`` conviction count. Shorts are considered
    only when ``allow_short`` (HL perps). Ties break on higher conviction.
    """
    best = None
    for sym, s in scores.items():
        if not isinstance(s, dict) or s.get("error"):
            continue
        signal = s.get("signal", "")
        score = float(s.get("score", 0) or 0)
        direction = s.get("direction", "FLAT")
        if score < threshold:
            continue
        if signal in _ACTIONABLE_LONG and direction == "LONG":
            side = "buy"
        elif signal in _ACTIONABLE_SHORT and direction == "SHORT" and allow_short:
            side = "sell"
        else:
            continue
        cand = {
            "symbol": sym, "side": side, "direction": direction,
            "signal": signal, "score": score,
            "entry": s.get("entry"), "stop": s.get("stop"), "target": s.get("target"),
        }
        if best is None or cand["score"] > best["score"]:
            best = cand
    return best


def decide_exits(held: list[dict], scores: dict[str, dict]) -> list[dict]:
    """Return positions to close: signal flipped against the position, or the
    name degraded to AVOID/WATCH (no longer a live trade).

    ``held`` items: {symbol, side} where side is "long"|"short".
    """
    out = []
    for pos in held:
        sym = pos.get("symbol")
        side = pos.get("side")
        s = scores.get(sym) if scores else None
        if not isinstance(s, dict):
            continue
        direction = s.get("direction", "FLAT")
        signal = s.get("signal", "")
        flipped = (side == "long" and direction == "SHORT") or (side == "short" and direction == "LONG")
        degraded = signal in ("AVOID", "WATCH")
        if flipped or degraded:
            out.append({"symbol": sym, "side": side,
                        "reason": "신호 반전" if flipped else "신호 소멸(AVOID/WATCH)"})
    return out


def stop_exits(positions: list[dict], tp_pct: float, sl_pct: float) -> list[dict]:
    """Hard take-profit / stop-loss check (not AI discretion). Returns positions
    to close with the realized move.

    ``positions`` items: {symbol, side("long"/"short"), entry, current}.
    ``tp_pct``/``sl_pct`` are fractions (0.15 = 15%). SL is given positive.
    """
    out = []
    for p in positions:
        entry, cur, side = p.get("entry"), p.get("current"), p.get("side")
        if not entry or not cur or entry <= 0:
            continue
        chg = (cur - entry) / entry
        pnl = chg if side == "long" else -chg  # short profits when price falls
        if pnl >= tp_pct:
            out.append({**p, "kind": "TAKE_PROFIT", "reason": f"익절 +{pnl*100:.1f}%"})
        elif pnl <= -abs(sl_pct):
            out.append({**p, "kind": "STOP_LOSS", "reason": f"손절 {pnl*100:.1f}%"})
    return out


def position_size(equity: float, position_pct: float, leverage: float, entry_price: float) -> float:
    """Notional-based size: equity × pct × leverage / entry. 0 if no price."""
    if not entry_price or entry_price <= 0:
        return 0.0
    notional = equity * position_pct * max(leverage, 1.0)
    return notional / entry_price
