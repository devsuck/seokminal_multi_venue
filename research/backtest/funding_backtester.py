"""Funding-aware 롱/숏 회계 엔진 (전략 아님, 정산기).

총 P&L = 가격변동 P&L + funding cashflow − 거래비용. 셋을 분리 저장(필수).

funding 부호 규약(perp): funding 양수 → long이 short에게 지급.
  funding_pnl = -side * notional * Σ(보유중 funding_rate)   (long=+1, short=-1)
  → long + 양수펀딩 = 음수, short + 양수펀딩 = 양수. 이 부호 틀리면 결과 완전 반전.
"""
from __future__ import annotations

import datetime as dt
import statistics as _st

SIDE = {"long": 1, "short": -1}


def position_pnl(
    entry_px: float,
    exit_px: float,
    side: str,
    notional: float,
    funding_sum: float,
    entry_cost_bps: float,
    exit_cost_bps: float,
) -> dict:
    """단일 포지션 정산. funding_sum = 보유 구간 funding_rate 합(비율).
    price/funding/cost 분리 반환."""
    s = SIDE[side]
    price_pnl = s * (exit_px - entry_px) / entry_px * notional
    funding_pnl = -s * notional * funding_sum
    trading_cost = notional * (entry_cost_bps + exit_cost_bps) / 10_000.0
    net = price_pnl + funding_pnl - trading_cost
    return {"side": side, "notional": notional,
            "price_pnl": round(price_pnl, 6), "funding_pnl": round(funding_pnl, 6),
            "trading_cost": round(trading_cost, 6), "net": round(net, 6)}


def aggregate_positions(positions: list[dict]) -> dict:
    """포지션 리스트 → 성분별 합 + 지표. price/funding/cost 반드시 분리 표시."""
    n = len(positions)
    if n == 0:
        return {"num_positions": 0, "price_pnl": 0.0, "funding_pnl": 0.0,
                "trading_cost": 0.0, "net_pnl": 0.0, "win_rate": 0.0,
                "net_per_trade": 0.0, "per_trade_sharpe": None, "underpowered": True}
    price = sum(p["price_pnl"] for p in positions)
    funding = sum(p["funding_pnl"] for p in positions)
    cost = sum(p["trading_cost"] for p in positions)
    nets = [p["net"] for p in positions]
    net = sum(nets)
    wins = sum(1 for x in nets if x > 0)
    sharpe = None
    if n >= 2:
        sd = _st.stdev(nets)
        if sd > 1e-12:
            sharpe = round(_st.mean(nets) / sd, 4)
    return {
        "num_positions": n,
        "price_pnl": round(price, 4), "funding_pnl": round(funding, 4),
        "trading_cost": round(cost, 4), "net_pnl": round(net, 4),
        "win_rate": round(wins / n, 4), "net_per_trade": round(net / n, 6),
        "per_trade_sharpe": sharpe, "underpowered": n < 30,
    }


# ── funding 시간당 → 일별 집계 ────────────────────────────────────────────────
def aggregate_funding_daily(times: list[int], rates: list[float]) -> dict:
    """UTC epoch(시간당) funding → {YYYY-MM-DD: 일별 funding 합}."""
    out: dict[str, float] = {}
    for t, r in zip(times, rates):
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d")
        out[d] = out.get(d, 0.0) + r
    return out


def funding_sum_over(daily_funding: dict, dates: list[str]) -> float:
    """보유 날짜들의 funding 합."""
    return sum(daily_funding.get(d, 0.0) for d in dates)


# ── 시점별 tradable universe (survivorship 방지) ─────────────────────────────
def tradable_at(date: str, close_by_coin: dict, min_prior_days: int = 30) -> list[str]:
    """리밸런스 시점 date에 실제 거래가능한 코인만.
    조건: 그 날 종가 존재 + 이전 min_prior_days 이상 데이터 존재(신규상장 배제).
    close_by_coin[coin] = {date: close} (정렬된 날짜)."""
    out = []
    for coin, series in close_by_coin.items():
        if date not in series:
            continue
        dates = sorted(series.keys())
        idx = dates.index(date)
        if idx >= min_prior_days:  # 충분한 과거 이력
            out.append(coin)
    return out
