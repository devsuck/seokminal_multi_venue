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

import datetime as _dt


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


def _shift_back(date_str: str, days: int) -> str:
    d = _dt.date.fromisoformat(date_str)
    return (d - _dt.timedelta(days=days)).isoformat()


def _ffill_align(series: list[dict], dates: list[str]) -> dict:
    """series=[{date,value}] (오름차순, FRED 응답 형식) → dates 축에 forward-fill 정렬."""
    svals = [(s["date"], s["value"]) for s in series if s["value"] is not None]
    out = {}
    idx = 0
    last = None
    for d in dates:
        while idx < len(svals) and svals[idx][0] <= d:
            last = svals[idx][1]
            idx += 1
        out[d] = last
    return out


def _cpi_yoy(series: list[dict]) -> list[dict]:
    """월간 CPI 레벨 → YoY %% 변화율 (12개월 전 대비), 앞 12개월은 계산 불가라 제외."""
    out = []
    for i in range(12, len(series)):
        v0 = series[i]["value"]
        v12 = series[i - 12]["value"]
        if v0 is None or v12 is None or v12 == 0:
            continue
        out.append({"date": series[i]["date"], "value": (v0 / v12 - 1.0) * 100.0})
    return out


def build_macro_panel(dates: list[str]) -> dict:
    """FRED 4개 시리즈를 GC 가격 패널의 날짜축(dates)에 정렬.

    real_rate = DGS10(명목 10년물) - CPI YoY(trailing 12개월, 근사 실질금리).
    """
    from fred.client import FREDClient

    client = FREDClient()
    start, end = dates[0], dates[-1]

    dgs10 = _ffill_align(client.get_series("DGS10", start, end), dates)
    cpi_raw = client.get_series("CPIAUCSL", start=_shift_back(start, 400), end=end)
    cpi = _ffill_align(_cpi_yoy(cpi_raw), dates)
    vix = _ffill_align(client.get_series("VIXCLS", start, end), dates)
    credit = _ffill_align(client.get_series("BAMLH0A0HYM2", start, end), dates)

    real_rate = {
        d: (dgs10[d] - cpi[d])
        for d in dates
        if dgs10.get(d) is not None and cpi.get(d) is not None
    }
    return {"dates": dates, "real_rate": real_rate, "vix": vix, "credit_spread": credit}
