"""멀티에셋 time-series momentum (TSMOM) — 가중치 함수 + 베이스라인.

각 자산: signal = sign(트레일링 lookback 수익률). vol targeting: weight = signal·target/realized(cap).
buyhold = signal 항상 +1(롱, 동일 vol타겟). random = 랜덤 ±1. 고정 파라미터·미최적화.
"""
from __future__ import annotations

import bisect
import statistics as _st

from research.data.intraday_store import load_df

DEFAULTS = {"lookback": 252, "vol_window": 60, "target_vol": 0.15, "cap": 3.0}


def build_panel(symbol: str) -> dict:
    df = load_df(symbol, "1d")
    if len(df) == 0:
        return {"symbol": symbol, "dates": [], "close": {}}
    import datetime as dt
    dates, close = [], {}
    for _, r in df.iterrows():
        d = dt.datetime.fromtimestamp(int(r["ts_utc"]), dt.timezone.utc).strftime("%Y-%m-%d")
        dates.append(d); close[d] = float(r["close"])
    return {"symbol": symbol, "dates": sorted(dates), "close": close}


def _asset_ctx(panel: dict, date: str, p: dict):
    """(signal_raw_mom, realized_vol) — date에 계산 가능하면, 아니면 None."""
    dates, close = panel["dates"], panel["close"]
    j = bisect.bisect_right(dates, date) - 1  # date 이하 마지막 인덱스
    if j < 0 or dates[j] != date:
        return None
    if j < max(p["lookback"], p["vol_window"]):
        return None
    mom = close[dates[j]] / close[dates[j - p["lookback"]]] - 1.0
    rets = [close[dates[k]] / close[dates[k - 1]] - 1.0 for k in range(j - p["vol_window"] + 1, j + 1)]
    vol = _st.stdev(rets) * (252 ** 0.5) if len(rets) >= 2 else 0.0
    return (mom, vol)


def _weight(signal: int, vol: float, p: dict) -> float:
    if vol <= 1e-9:
        return 0.0
    return signal * min(p["target_vol"] / vol, p["cap"])


def tsmom_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        ctx = _asset_ctx(pn, date, p)
        if ctx is None:
            continue
        mom, vol = ctx
        out[a] = _weight(1 if mom > 0 else -1, vol, p)
    return out


def buyhold_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    """항상 롱(동일 vol 타겟) — 모멘텀 타이밍 가치 격리용 베이스라인."""
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        ctx = _asset_ctx(pn, date, p)
        if ctx is None:
            continue
        _, vol = ctx
        out[a] = _weight(1, vol, p)
    return out


def random_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    """랜덤 ±1(동일 vol 타겟). random 베이스라인."""
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        ctx = _asset_ctx(pn, date, p)
        if ctx is None:
            continue
        _, vol = ctx
        s = 1 if (rng.random() < 0.5 if rng else True) else -1
        out[a] = _weight(s, vol, p)
    return out
