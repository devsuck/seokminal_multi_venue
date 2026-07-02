"""Funding 가설(perp-only, 고정 파라미터·미최적화) + funding-aware random baseline.

가설1 funding extreme reversal: funding z-score 극단 → 반대 포지션, 3d 홀딩.
가설2 cross-sectional funding: trailing funding 하위 롱/상위 숏, 1d 리밸런스.
판정은 pull 완료 후. 지금은 회계 배선 + synthetic 검증만.
"""
from __future__ import annotations

import random as _random
import statistics as _st

from research.data.intraday_store import load_df as _load_bars
from research.data.funding_store import load_series as _load_funding
from research.backtest.funding_backtester import (
    position_pnl, aggregate_positions, aggregate_funding_daily, funding_sum_over, tradable_at,
)
from research.validation.cost_model import hl_effective_cost_bps

NOTIONAL = 10_000.0
HL_COST = hl_effective_cost_bps("major", taker=True)  # 체결당 bps

DEFAULTS_REVERSAL = {"z_window": 30, "trail": 3, "z_entry": 2.0, "hold_days": 3}
# rebalance_days=1 기본(하위호환). weekly=7. cost_bps 미지정 시 HL taker(major).
DEFAULTS_XSECT = {"trail": 3, "basket_pct": 0.2, "min_prior_days": 30, "rebalance_days": 1}


def build_daily_panel(coin: str) -> dict:
    """일봉 close(날짜별) + 일별 funding 합. 없으면 빈 패널."""
    bars = _load_bars(coin, "1d")
    fund = _load_funding(coin)
    if len(bars) == 0 or not fund["time"]:
        return {"coin": coin, "dates": [], "close": {}, "daily_funding": {}}
    import datetime as dt
    close = {}
    for _, r in bars.iterrows():
        d = dt.datetime.fromtimestamp(int(r["ts_utc"]), dt.timezone.utc).strftime("%Y-%m-%d")
        close[d] = float(r["close"])
    daily_funding = aggregate_funding_daily(fund["time"], fund["funding_rate"])
    dates = sorted(set(close.keys()) & set(daily_funding.keys()))
    return {"coin": coin, "dates": dates, "close": close, "daily_funding": daily_funding}


# ── 가설1: funding extreme reversal ──────────────────────────────────────────
def funding_extreme_reversal(panel: dict, params: dict | None = None) -> list[dict]:
    p = {**DEFAULTS_REVERSAL, **(params or {})}
    dates, close, df = panel["dates"], panel["close"], panel["daily_funding"]
    zw, trail, ze, hold = p["z_window"], p["trail"], p["z_entry"], p["hold_days"]
    fr = [df[d] for d in dates]  # 일별 funding
    trail_avg = [None] * len(dates)
    for i in range(len(dates)):
        if i >= trail:
            trail_avg[i] = sum(fr[i - trail:i]) / trail
    positions = []
    i = zw + trail
    while i + hold < len(dates):
        window = [trail_avg[j] for j in range(i - zw, i) if trail_avg[j] is not None]
        cur = trail_avg[i]
        if cur is None or len(window) < zw // 2:
            i += 1; continue
        mu, sd = _st.mean(window), (_st.stdev(window) if len(window) >= 2 else 0.0)
        if sd <= 1e-12:
            i += 1; continue
        z = (cur - mu) / sd
        side = None
        if z > ze:
            side = "short"   # long 과밀(양수펀딩 극단) → 반전 숏
        elif z < -ze:
            side = "long"    # short 과밀 → 반전 롱
        if side:
            hold_dates = dates[i + 1:i + 1 + hold]
            positions.append(position_pnl(
                close[dates[i]], close[dates[i + hold]], side, NOTIONAL,
                funding_sum_over(df, hold_dates), HL_COST, HL_COST))
            i += hold  # 중첩 금지
        else:
            i += 1
    return positions


def random_reversal(panel: dict, n_positions: int, hold: int, n_runs: int, seed: int) -> list[float]:
    """funding-aware random: 같은 수·같은 홀딩, 랜덤 진입일·랜덤 사이드, 실제 가격·funding."""
    dates, close, df = panel["dates"], panel["close"], panel["daily_funding"]
    valid = [i for i in range(len(dates) - hold - 1)]
    if n_positions <= 0 or len(valid) < n_positions:
        return [0.0] * n_runs
    rng = _random.Random(seed)
    out = []
    for _ in range(n_runs):
        idxs = rng.sample(valid, n_positions)
        tot = 0.0
        for i in range(len(idxs)):
            side = rng.choice(["long", "short"])
            hd = dates[idxs[i] + 1:idxs[i] + 1 + hold]
            tot += position_pnl(close[dates[idxs[i]]], close[dates[idxs[i] + hold]], side,
                                NOTIONAL, funding_sum_over(df, hd), HL_COST, HL_COST)["net"]
        out.append(round(tot, 4))
    return out


# ── 가설2: cross-sectional funding ───────────────────────────────────────────
def _xsect_schedule(panels: dict, params: dict) -> list[tuple]:
    """리밸런스 스케줄: [(d, dn, hold_dates, scored=[(coin, trailing_funding)], nb)].
    rebalance_days 간격(1=daily, 7=weekly). hold_dates=보유기간(funding 누적).
    전략·random이 동일 스케줄·바스켓크기 → 공정 비교."""
    p = {**DEFAULTS_XSECT, **params}
    trail, bpct, minp, step = p["trail"], p["basket_pct"], p["min_prior_days"], int(p["rebalance_days"])
    close_by = {c: pn["close"] for c, pn in panels.items()}
    all_dates = sorted(set().union(*[set(pn["dates"]) for pn in panels.values()])) if panels else []
    sched = []
    for di in range(0, len(all_dates) - step, step):
        d, dn = all_dates[di], all_dates[di + step]
        hold_dates = all_dates[di:di + step]  # 보유일들(funding 누적)
        uni = tradable_at(d, close_by, minp)
        scored = []
        for c in uni:
            pn = panels[c]; ds = pn["dates"]
            if d not in pn["close"] or dn not in pn["close"] or d not in pn["daily_funding"] or d not in ds:
                continue
            k = ds.index(d)
            if k < trail:
                continue
            tavg = sum(pn["daily_funding"].get(ds[j], 0.0) for j in range(k - trail, k)) / trail
            scored.append((c, tavg))
        if len(scored) < 5:
            continue
        nb = max(1, int(len(scored) * bpct))
        sched.append((d, dn, hold_dates, scored, nb))
    return sched


def _xsect_position(panels, coin, d, dn, hold_dates, side, cost_bps):
    pn = panels[coin]
    fsum = sum(pn["daily_funding"].get(dd, 0.0) for dd in hold_dates)  # 보유기간 funding 누적
    return position_pnl(pn["close"][d], pn["close"][dn], side, NOTIONAL, fsum, cost_bps, cost_bps)


def cross_sectional_funding(panels: dict, params: dict | None = None) -> list[dict]:
    """리밸런스: trailing funding 하위 롱 / 상위 숏(동일가중). rebalance_days로 빈도."""
    params = params or {}
    cost = params.get("cost_bps", HL_COST)
    sched = _xsect_schedule(panels, params)
    positions = []
    for d, dn, hold_dates, scored, nb in sched:
        scored = sorted(scored, key=lambda x: x[1])
        for c, _ in scored[:nb]:
            positions.append(_xsect_position(panels, c, d, dn, hold_dates, "long", cost))
        for c, _ in scored[-nb:]:
            positions.append(_xsect_position(panels, c, d, dn, hold_dates, "short", cost))
    return positions


def random_cross_sectional(panels: dict, params: dict | None, n_runs: int, seed: int) -> list[float]:
    """동일 스케줄·롱숏 수·홀딩·비용, 랜덤 코인 → run별 net 합 분포(funding-aware)."""
    params = params or {}
    cost = params.get("cost_bps", HL_COST)
    sched = _xsect_schedule(panels, params)
    rng = _random.Random(seed)
    out = []
    for _ in range(n_runs):
        tot = 0.0
        for d, dn, hold_dates, scored, nb in sched:
            coins = [c for c, _ in scored]
            picks = rng.sample(coins, min(len(coins), 2 * nb))
            for c in picks[:nb]:
                tot += _xsect_position(panels, c, d, dn, hold_dates, "long", cost)["net"]
            for c in picks[nb:2 * nb]:
                tot += _xsect_position(panels, c, d, dn, hold_dates, "short", cost)["net"]
        out.append(round(tot, 4))
    return out
