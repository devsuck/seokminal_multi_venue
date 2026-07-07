"""금(GC) 안전자산 가설 — 실질금리 하락 레짐 게이트 + VIX/신용스프레드 리스크오프 부스트.

롱/플랫만(숏 없음). 게이트가 BULLISH일 때만 포지션 보유, 리스크오프는 크기만 조절
(게이트가 FLAT이면 리스크오프여도 무포지션). 상세: docs/superpowers/specs/2026-07-07-gold-haven-hypothesis-design.md
"""
from __future__ import annotations

import bisect
import statistics as _st

DEFAULTS = {
    "real_rate_lookback": 63,
    "vol_window": 60,
    "risk_off_zscore_window": 252,
    "risk_off_zscore_threshold": 1.5,
    "risk_off_boost": 1.5,
    "target_vol": 0.15,
    "cap": 3.0,
}


def _bisect_at(dates: list, date: str) -> int | None:
    j = bisect.bisect_right(dates, date) - 1
    if j < 0 or dates[j] != date:
        return None
    return j


def _asset_vol(panel: dict, date: str, vol_window: int) -> float | None:
    dates, close = panel["dates"], panel["close"]
    j = _bisect_at(dates, date)
    if j is None or j < vol_window:
        return None
    rets = [close[dates[k]] / close[dates[k - 1]] - 1.0 for k in range(j - vol_window + 1, j + 1)]
    return _st.stdev(rets) * (252 ** 0.5) if len(rets) >= 2 else 0.0


def _regime_gate(macro: dict, date: str, lookback: int) -> str | None:
    """BULLISH(실질금리 lookback일 전보다 하락)/FLAT/None(이력부족)."""
    dates = macro["dates"]
    j = _bisect_at(dates, date)
    if j is None or j < lookback:
        return None
    now = macro["real_rate"].get(dates[j])
    past = macro["real_rate"].get(dates[j - lookback])
    if now is None or past is None:
        return None
    return "BULLISH" if now < past else "FLAT"


def _zscore_last(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _st.mean(values)
    std = _st.stdev(values)
    return (values[-1] - mean) / std if std > 1e-9 else 0.0


def _risk_off(macro: dict, date: str, window: int, threshold: float) -> bool:
    dates = macro["dates"]
    j = _bisect_at(dates, date)
    if j is None or j < window:
        return False
    span = range(j - window + 1, j + 1)

    vix_vals = [macro["vix"].get(dates[k]) for k in span]
    if all(v is not None for v in vix_vals) and _zscore_last(vix_vals) > threshold:
        return True

    credit_vals = [macro["credit_spread"].get(dates[k]) for k in span]
    if all(v is not None for v in credit_vals) and _zscore_last(credit_vals) > threshold:
        return True

    return False


def gold_haven_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    p = {**DEFAULTS, **params}
    macro = p["macro"]
    gate = _regime_gate(macro, date, p["real_rate_lookback"])
    out = {}
    for a, pn in panels.items():
        vol = _asset_vol(pn, date, p["vol_window"])
        if vol is None:
            continue
        if gate != "BULLISH":
            out[a] = 0.0
            continue
        boost = p["risk_off_boost"] if _risk_off(
            macro, date, p["risk_off_zscore_window"], p["risk_off_zscore_threshold"]
        ) else 1.0
        base = (p["target_vol"] / vol) if vol > 1e-9 else 0.0
        out[a] = min(base * boost, p["cap"])
    return out


def buyhold_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    """항상 롱(동일 vol 타겟) — 타이밍 가치 격리용 베이스라인."""
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        vol = _asset_vol(pn, date, p["vol_window"])
        if vol is None:
            continue
        out[a] = min(p["target_vol"] / vol, p["cap"]) if vol > 1e-9 else 0.0
    return out


def random_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    """같은 빈도로 무작위 온(롱)/오프(플랫). 숏 없음 → 0/1 랜덤(TSMOM의 ±1과 다름)."""
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        vol = _asset_vol(pn, date, p["vol_window"])
        if vol is None:
            continue
        on = (rng.random() < 0.5) if rng else True
        out[a] = (min(p["target_vol"] / vol, p["cap"]) if vol > 1e-9 else 0.0) if on else 0.0
    return out
