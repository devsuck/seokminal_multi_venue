"""Post-Trade 벤치마크 (P8.7) — 순수 함수. 결정적·부작용 없음.

Arrival · Decision · VWAP · TWAP · Close · Implementation Shortfall · Effective/Realized Spread ·
Market Impact · Opportunity Cost · Slippage/Cost Attribution. **집행/브로커/포지션 무관.**
"""
from __future__ import annotations

_BPS = 10_000.0
_EPS = 1e-12


def _sign(side: str) -> float:
    """불리한 방향 부호. BUY: 비쌀수록 손해(+). SELL: 쌀수록 손해(+)."""
    return 1.0 if side == "BUY" else -1.0


def dedup_fills(fills: list) -> list:
    seen, out = set(), []
    for f in fills:
        d = f if isinstance(f, dict) else f.to_dict()
        fid = d.get("fill_id", id(f))
        if fid in seen:
            continue
        seen.add(fid)
        out.append(d)
    return out


def total_quantity(fills: list) -> float:
    return round(sum(float(f.get("quantity", 0.0)) for f in dedup_fills(fills)), 8)


def vwap(fills: list) -> float | None:
    ded = dedup_fills(fills)
    tq = sum(float(f.get("quantity", 0.0)) for f in ded)
    if abs(tq) < _EPS:
        return None
    return round(sum(float(f.get("quantity", 0.0)) * float(f.get("fill_price", 0.0))
                     for f in ded) / tq, 8)


def twap(fills: list) -> float | None:
    """등간격 시간가중 근사 = 체결가 단순평균."""
    ded = dedup_fills(fills)
    if not ded:
        return None
    return round(sum(float(f.get("fill_price", 0.0)) for f in ded) / len(ded), 8)


def slippage_bps(side: str, benchmark: float | None, execution_price: float | None) -> float | None:
    """벤치마크 대비 불리 슬리피지(bps). 불리 = 양(+)."""
    if benchmark is None or execution_price is None or abs(benchmark) < _EPS:
        return None
    return round(_sign(side) * (execution_price - benchmark) / abs(benchmark) * _BPS, 8)


def implementation_shortfall_bps(side: str, decision_price: float | None,
                                 execution_price: float | None) -> float | None:
    return slippage_bps(side, decision_price, execution_price)


def market_impact_bps(side: str, arrival_price: float | None,
                      execution_price: float | None) -> float | None:
    return slippage_bps(side, arrival_price, execution_price)


def effective_spread_bps(execution_price: float | None, mid_price: float | None) -> float | None:
    if execution_price is None or mid_price is None or abs(mid_price) < _EPS:
        return None
    return round(2.0 * abs(execution_price - mid_price) / abs(mid_price) * _BPS, 8)


def realized_spread_bps(side: str, execution_price: float | None,
                        future_mid_price: float | None) -> float | None:
    if execution_price is None or future_mid_price is None or abs(future_mid_price) < _EPS:
        return None
    return round(2.0 * _sign(side) * (execution_price - future_mid_price)
                 / abs(future_mid_price) * _BPS, 8)


def opportunity_cost(side: str, unfilled_quantity: float, decision_price: float | None,
                     close_price: float | None) -> float | None:
    if decision_price is None or close_price is None or unfilled_quantity <= _EPS:
        return 0.0
    return round(_sign(side) * unfilled_quantity * (close_price - decision_price), 8)
