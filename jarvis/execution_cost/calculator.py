"""Execution Cost Calculator (P8.4) — 순수 회계 함수. 결정적·부작용 없음.

gross = qty×fill. slippage(BUY: fill−exp / SELL: exp−fill)/exp. spread |fill−mid|/mid.
commission/exchange/fx = gross×rate. total = 각 비용 합. cost_bps = total/gross×10000.
**집행/브로커/포지션 무관.**
"""
from __future__ import annotations

from jarvis.execution_cost.models import CostComponents, CostRates

_BPS = 10_000.0
_EPS = 1e-12


def gross_value(quantity: float, fill_price: float) -> float:
    return round(float(quantity) * float(fill_price), 8)


def slippage_bps(side: str, expected_price: float, fill_price: float) -> float:
    """불리한 체결이 양(+). BUY: 비싸게 = 양. SELL: 싸게 = 양."""
    base = abs(expected_price) or _EPS
    if side == "BUY":
        ratio = (fill_price - expected_price) / base
    elif side == "SELL":
        ratio = (expected_price - fill_price) / base
    else:
        ratio = 0.0
    return round(ratio * _BPS, 8)


def spread_bps(fill_price: float, mid_price: float) -> float:
    base = abs(mid_price) or _EPS
    return round(abs(fill_price - mid_price) / base * _BPS, 8)


def _to_currency(bps: float, gross: float) -> float:
    return round(bps / _BPS * gross, 8)


def calculate(inp, rates: CostRates | None = None, mid_price: float | None = None) -> CostComponents:
    """모든 비용 구성요소 산출. mid_price 미지정 시 expected_price 사용(스프레드 프록시)."""
    rates = rates or CostRates()
    d = inp.to_dict() if hasattr(inp, "to_dict") else inp
    gross = float(d["gross_value"])
    exp_p = float(d["expected_price"])
    fill_p = float(d["fill_price"])
    side = d["side"]
    mid = float(mid_price) if mid_price is not None else exp_p

    commission = round(gross * rates.commission_rate, 8)
    exchange_fee = round(gross * rates.exchange_fee_rate, 8)
    fx_cost = round(gross * rates.fx_rate_cost, 8)
    market_impact_cost = round(gross * rates.market_impact_rate, 8)
    slippage_cost = _to_currency(slippage_bps(side, exp_p, fill_p), gross)
    spread_cost = _to_currency(spread_bps(fill_p, mid), gross)

    total = round(commission + exchange_fee + spread_cost + slippage_cost
                  + market_impact_cost + fx_cost, 8)
    return CostComponents(
        commission=commission, exchange_fee=exchange_fee, spread_cost=spread_cost,
        slippage_cost=slippage_cost, market_impact_cost=market_impact_cost,
        fx_cost=fx_cost, total_cost=total)


def cost_bps(total_cost: float, gross_value_: float) -> float:
    base = abs(gross_value_) or _EPS
    return round(total_cost / base * _BPS, 8)
