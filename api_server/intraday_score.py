"""Professional-grade intraday (day-trading) scoring engine.

Pure functions over a list of intraday bars (5-minute), producing a directional
signal with conviction and ATR-based risk levels. This is a *day-trading* model,
not the daily value/multifactor model used for swing trades:

  - VWAP is the institutional intraday anchor (trend filter + mean-reversion ref)
  - Opening-Range Breakout (ORB) is the primary entry trigger
  - Relative volume (RVOL) confirms real participation (filters fake breakouts)
  - EMA9/EMA20 stack on 5-min bars defines the micro-trend
  - ATR sizes stops/targets (1.5R) and gates out dead, untradeable names
  - RSI(7) flags intraday over-extension (don't chase)
  - Time-of-day dampens the midday chop

A bar is a mapping with keys: t (datetime, tz-aware UTC), o, h, l, c, v.
All scoring is deterministic given the bars, so it is fully unit-testable; the
network fetch lives in the endpoint, not here.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_KST = ZoneInfo("Asia/Seoul")
_TZ_BY_MARKET = {"US": _ET, "KR": _KST}

# 5-min bars: 30-min opening range = 6 bars.
_OPENING_RANGE_BARS = 6
_BAR_MINUTES = 5


def _f(bar, k):
    return float(bar[k])


def session_bars(bars: list[dict], tz=_ET) -> list[dict]:
    """Keep only the most recent session's bars in ``tz`` (VWAP/ORB reset daily)."""
    if not bars:
        return []
    def sday(b):
        t: datetime = b["t"]
        return t.astimezone(tz).date()
    last_day = sday(bars[-1])
    return [b for b in bars if sday(b) == last_day]


def vwap(bars: list[dict]) -> float:
    num = den = 0.0
    for b in bars:
        tp = (_f(b, "h") + _f(b, "l") + _f(b, "c")) / 3
        v = _f(b, "v")
        num += tp * v
        den += v
    return num / den if den > 0 else (_f(bars[-1], "c") if bars else 0.0)


def opening_range(bars: list[dict]) -> tuple[float, float]:
    head = bars[:_OPENING_RANGE_BARS]
    if not head:
        return 0.0, 0.0
    return max(_f(b, "h") for b in head), min(_f(b, "l") for b in head)


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values: list[float], period: int = 7) -> float:
    if len(values) <= period:
        return 50.0
    gains = losses = 0.0
    for i in range(len(values) - period, len(values)):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)


def atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l = _f(bars[i], "h"), _f(bars[i], "l")
        prev_c = _f(bars[i - 1], "c")
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    window = trs[-period:] if len(trs) >= period else trs
    return sum(window) / len(window) if window else 0.0


def relative_volume(bars: list[dict]) -> float:
    """Latest bar volume vs the average of the session's prior bars."""
    if len(bars) < 2:
        return 1.0
    prior = [_f(b, "v") for b in bars[:-1]]
    avg = sum(prior) / len(prior) if prior else 0.0
    return _f(bars[-1], "v") / avg if avg > 0 else 1.0


def _time_of_day_factor(t_et: time) -> float:
    """Down-weight the low-conviction midday chop (11:30–13:30 ET)."""
    if time(11, 30) <= t_et <= time(13, 30):
        return 0.7
    return 1.0


def score_intraday(
    bars: list[dict], price_floor_atr_pct: float = 0.003, crypto: bool = False,
    market: str = "US",
) -> dict:
    """Composite intraday signal. Returns direction, conviction (0-100), signal,
    component breakdown, and ATR-based entry/stop/target.

    ``price_floor_atr_pct`` is the minimum ATR/price for a name to be tradeable;
    below it the market is too dead to day-trade and we force AVOID.

    ``crypto`` adapts the model for 24/7 perps: no ET-session reset (the caller
    passes a rolling ~24h window), VWAP is rolling over that window, the
    "opening range" becomes the leading-bars range as a rolling breakout
    reference, and the midday time-of-day damp is disabled.
    """
    # Equity: reset to the latest cash session in the market's tz (ET/KST).
    # Crypto: rolling window as-is (24/7).
    sb = bars if crypto else session_bars(bars, _TZ_BY_MARKET.get(market, _ET))
    if len(sb) < _OPENING_RANGE_BARS + 2:
        return {"direction": "FLAT", "score": 0, "signal": "AVOID",
                "reason": "insufficient intraday data", "components": {}}

    closes = [_f(b, "c") for b in sb]
    price = closes[-1]
    vw = vwap(sb)
    or_high, or_low = opening_range(sb)
    ema9, ema20 = ema(closes, 9), ema(closes, 20)
    a = atr(sb)
    rv = relative_volume(sb)
    r7 = rsi(closes, 7)
    atr_pct = a / price if price > 0 else 0.0

    components: dict[str, dict] = {}
    score = 0.0

    # ── 1. Regime: VWAP + EMA stack (max 25) → sets direction ──────────────────
    above_vwap = price > vw
    ema_bull = ema9 > ema20
    if above_vwap and ema_bull:
        direction, regime_pts, regime_lbl = "LONG", 25, "VWAP 위 + EMA 정배열 (강세)"
    elif (not above_vwap) and (not ema_bull):
        direction, regime_pts, regime_lbl = "SHORT", 25, "VWAP 아래 + EMA 역배열 (약세)"
    elif above_vwap:
        direction, regime_pts, regime_lbl = "LONG", 12, "VWAP 위, EMA 혼조"
    else:
        direction, regime_pts, regime_lbl = "SHORT", 12, "VWAP 아래, EMA 혼조"
    score += regime_pts
    components["regime"] = {"vwap": round(vw, 2), "price": round(price, 2),
                            "ema9": round(ema9, 2), "ema20": round(ema20, 2),
                            "score": regime_pts, "label": regime_lbl}

    # ── 2. ORB trigger (max 25) ────────────────────────────────────────────────
    if direction == "LONG":
        if price > or_high:
            orb_pts, orb_lbl = 25, "개장레인지 상단 돌파"
        elif or_high > 0 and price > or_high - a:
            orb_pts, orb_lbl = 12, "상단 돌파 임박"
        else:
            orb_pts, orb_lbl = 4, "레인지 내부"
    else:  # SHORT
        if or_low > 0 and price < or_low:
            orb_pts, orb_lbl = 25, "개장레인지 하단 이탈"
        elif or_low > 0 and price < or_low + a:
            orb_pts, orb_lbl = 12, "하단 이탈 임박"
        else:
            orb_pts, orb_lbl = 4, "레인지 내부"
    score += orb_pts
    components["orb"] = {"or_high": round(or_high, 2), "or_low": round(or_low, 2),
                         "score": orb_pts, "label": orb_lbl}

    # ── 3. RVOL confirmation (max 20) ──────────────────────────────────────────
    if rv >= 2.0:
        rvol_pts, rvol_lbl = 20, f"RVOL {rv:.1f}x 폭발적"
    elif rv >= 1.5:
        rvol_pts, rvol_lbl = 15, f"RVOL {rv:.1f}x 강함"
    elif rv >= 1.0:
        rvol_pts, rvol_lbl = 8, f"RVOL {rv:.1f}x 보통"
    else:
        rvol_pts, rvol_lbl = 0, f"RVOL {rv:.1f}x 참여 부족"
    score += rvol_pts
    components["rvol"] = {"value": round(rv, 2), "score": rvol_pts, "label": rvol_lbl}

    # ── 4. Micro-momentum aligned with regime (max 15) ─────────────────────────
    last3 = closes[-4:]
    mom_pts = 0
    if len(last3) == 4:
        up = sum(1 for i in range(1, 4) if last3[i] > last3[i - 1])
        down = 3 - up
        if direction == "LONG" and up >= 2:
            mom_pts = 15 if up == 3 else 9
        elif direction == "SHORT" and down >= 2:
            mom_pts = 15 if down == 3 else 9
    score += mom_pts
    components["momentum"] = {"score": mom_pts, "label": f"최근 3봉 정렬 ({direction})"}

    # ── 5. Volatility gate (max 15, or hard AVOID) ─────────────────────────────
    if atr_pct < price_floor_atr_pct:
        components["volatility"] = {"atr_pct": round(atr_pct * 100, 3),
                                    "score": 0, "label": "변동성 부족 — 단타 부적합"}
        return {"direction": "FLAT", "score": 0, "signal": "AVOID",
                "reason": f"ATR {atr_pct*100:.2f}% < {price_floor_atr_pct*100:.2f}% (죽은 종목)",
                "vwap": round(vw, 2), "atr": round(a, 3), "rvol": round(rv, 2),
                "rsi7": round(r7, 1), "components": components}
    if atr_pct <= 0.03:
        vol_pts, vol_lbl = 15, f"ATR {atr_pct*100:.2f}% 적정 변동성"
    else:
        vol_pts, vol_lbl = 6, f"ATR {atr_pct*100:.2f}% 과변동 (리스크↑)"
    score += vol_pts
    components["volatility"] = {"atr_pct": round(atr_pct * 100, 3), "score": vol_pts, "label": vol_lbl}

    # ── 6. Over-extension penalty (RSI7) — don't chase ─────────────────────────
    ext_penalty = 0
    if direction == "LONG" and r7 > 85:
        ext_penalty = -20
    elif direction == "SHORT" and r7 < 15:
        ext_penalty = -20
    score += ext_penalty
    components["extension"] = {"rsi7": round(r7, 1), "score": ext_penalty,
                               "label": "과열 추격 위험" if ext_penalty else "정상"}

    # ── 7. Time-of-day damp (US equities only; crypto 24/7, KR skip for now) ───
    if crypto or market != "US":
        tod = 1.0
        components["time_of_day"] = {"et": "24/7" if crypto else market, "factor": tod}
    else:
        t_et = sb[-1]["t"].astimezone(_ET).time()
        tod = _time_of_day_factor(t_et)
        components["time_of_day"] = {"et": t_et.strftime("%H:%M"), "factor": tod}
    score = max(0.0, score) * tod

    score = round(min(score, 100.0), 1)

    # ── Signal mapping + ATR risk levels ───────────────────────────────────────
    if score >= 70:
        signal = "STRONG_" + ("BUY" if direction == "LONG" else "SELL")
    elif score >= 55:
        signal = "BUY" if direction == "LONG" else "SELL"
    elif score >= 40:
        signal = "WATCH"
    else:
        signal = "AVOID"

    if direction == "LONG":
        entry, stop, target = price, price - a, price + 1.5 * a
    else:
        entry, stop, target = price, price + a, price - 1.5 * a

    return {
        "direction": direction,
        "score": score,
        "max_score": 100,
        "signal": signal,
        "price": round(price, 2),
        "vwap": round(vw, 2),
        "atr": round(a, 3),
        "rvol": round(rv, 2),
        "rsi7": round(r7, 1),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "rr": 1.5,
        "components": components,
    }
