"""수익률 기반 멀티에셋 포트폴리오 백테스터 (TSMOM용, 이산거래 아님).

각 리밸런스에 weight_fn이 자산별 타겟 비중 산출 → 다음 리밸런스까지 보유.
일간 포트 수익률 = (1/N)Σ w_a·ret_a. 리밸런스 시 턴오버 비용 차감. vol targeting은 weight_fn 담당.
자산별 자기 이력만 사용(시점별, lookahead 없음)."""
from __future__ import annotations

import math
import statistics as _st
from typing import Callable

TRADING_DAYS = 252

# weight_fn(panels, date, params, rng) -> {asset: weight}  (해당 date에 tradable 자산만)
WeightFn = Callable[[dict, str, dict, object], dict]


def _daily_returns(closes: dict, dates: list[str]) -> dict:
    """자산 close(date->px) → date->일간수익률(전일 대비)."""
    out = {}
    prev = None
    for d in dates:
        if d in closes:
            if prev is not None and prev in closes and closes[prev] > 0:
                out[d] = closes[d] / closes[prev] - 1
            prev = d
    return out


def run_portfolio(
    panels: dict,
    weight_fn: WeightFn,
    params: dict | None = None,
    cost_bps: float = 2.0,
    rebalance_days: int = 21,
    rng: object = None,
) -> dict:
    """반환: {daily_returns:[], dates:[], metrics:{...}}."""
    params = params or {}
    all_dates = sorted(set().union(*[set(p["dates"]) for p in panels.values()])) if panels else []
    rets_by = {a: _daily_returns(p["close"], all_dates) for a, p in panels.items()}
    weights: dict = {}
    daily = []
    out_dates = []
    prev_d = None
    for i, d in enumerate(all_dates):
        if prev_d is not None:
            active = [a for a in weights if d in rets_by[a]]
            r = sum(weights[a] * rets_by[a][d] for a in active)
            n = len([a for a in weights if weights[a] != 0]) or 1
            r = r / n
            if i % rebalance_days == 0:
                new_w = weight_fn(panels, d, params, rng)
                allk = set(weights) | set(new_w)
                turnover = sum(abs(new_w.get(a, 0.0) - weights.get(a, 0.0)) for a in allk)
                r -= turnover * cost_bps / 10_000.0 / n
                weights = new_w
            daily.append(r)
            out_dates.append(d)
        else:
            weights = weight_fn(panels, d, params, rng)
        prev_d = d
    return {"daily_returns": daily, "dates": out_dates, "metrics": portfolio_metrics(daily)}


def portfolio_metrics(daily: list[float]) -> dict:
    n = len(daily)
    if n < 2:
        return {"days": n, "ann_return": 0.0, "ann_vol": 0.0, "sharpe": None,
                "total_return": 0.0, "max_drawdown": 0.0, "underpowered": True}
    mean = _st.mean(daily)
    vol = _st.stdev(daily)
    ann_ret = mean * TRADING_DAYS
    ann_vol = vol * math.sqrt(TRADING_DAYS)
    sharpe = (ann_ret / ann_vol) if ann_vol > 1e-12 else None
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in daily:
        eq *= (1 + r)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    return {
        "days": n,
        "ann_return": round(ann_ret, 4), "ann_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "total_return": round(eq - 1, 4), "max_drawdown": round(mdd, 4),
        "underpowered": n < 252,  # 1년 미만 = 검정력 약함
    }
