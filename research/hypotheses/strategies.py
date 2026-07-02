"""가설 5종 signal 생성 함수 (롱온리, 고정 파라미터·미최적화).

각 함수: (ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}
feat = runner.common_features 결과(sids/mso/vwap/atr_abs). eligible = opportunity set.
"""
from __future__ import annotations

from xgb_strategy.labeling import atr_pct
from research.data.intraday_store import load_ohlc_lists
from research.features.opening_range import opening_range
from research.features.rvol import rvol as _rvol
from research.features.indicators import ema as _ema, rsi as _rsi

INTRADAY_TF = "15m"

# 섹터 매핑(유동성 종목 → 보유 섹터 ETF; XLC 미보유라 통신주는 XLK 근사)
SECTOR_MAP = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "AVGO": "XLK",
    "GOOGL": "XLK", "META": "XLK", "NFLX": "XLK",
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY",
    "JPM": "XLF", "V": "XLF", "MA": "XLF",
    "UNH": "XLV", "JNJ": "XLV",
    "COST": "XLP", "WMT": "XLP", "PG": "XLP",
    "XOM": "XLE",
}


# ── 1. VWAP 평균회귀 ──────────────────────────────────────────────────────────
def vwap_mean_reversion(ohlc, feat, aux, params):
    c, vwap, mso, atr = ohlc["close"], feat["vwap"], feat["mso"], feat["atr_abs"]
    r = _rsi(c, 14)
    dev_k = params.get("dev_k", 0.004); rsi_max = params.get("rsi_max", 35.0); orm = params.get("or_minutes", 30)
    n = len(c); entry = [False] * n; elig = []
    for i in range(n):
        if not (mso[i] >= orm and vwap[i] and atr[i] and r[i] is not None):
            continue
        elig.append(i)
        dev = (c[i] - vwap[i]) / vwap[i]
        if dev < -dev_k and r[i] < rsi_max:
            entry[i] = True
    return {"entry": entry, "eligible": elig}


# ── 2. ORB 실패돌파 반전 (bear trap → 롱) ─────────────────────────────────────
def orb_failed_reversal(ohlc, feat, aux, params):
    h, l, c = ohlc["high"], ohlc["low"], ohlc["close"]
    mso, atr, sids = feat["mso"], feat["atr_abs"], feat["sids"]
    orm = params.get("or_minutes", 30)
    orr = opening_range(h, l, sids, mso, orm)
    n = len(c); entry = [False] * n; elig = []
    for i in range(1, n):
        if not (mso[i] >= orm and orr["or_low"][i] is not None and atr[i]):
            continue
        elig.append(i)
        # 직전 봉 OR low 하향이탈 후 현재 종가가 OR low 위로 회복 = 실패 돌파
        if l[i - 1] < orr["or_low"][i] and c[i] > orr["or_low"][i]:
            entry[i] = True
    return {"entry": entry, "eligible": elig}


# ── 3. 갭업 지속 ─────────────────────────────────────────────────────────────
def gap_continuation(ohlc, feat, aux, params):
    o, c = ohlc["open"], ohlc["close"]
    vwap, mso, atr, sids = feat["vwap"], feat["mso"], feat["atr_abs"], feat["sids"]
    gap_k = params.get("gap_k", 0.005)
    n = len(c)
    sess_open = {}; sess_last = {}; order = []
    for i in range(n):
        s = sids[i]
        if s not in sess_open:
            sess_open[s] = o[i]; order.append(s)
        sess_last[s] = c[i]
    prev_close = {order[k]: sess_last[order[k - 1]] for k in range(1, len(order))}
    entry = [False] * n; elig = []
    for i in range(n):
        s = sids[i]
        if not (15 <= mso[i] <= 60 and vwap[i] and atr[i] and s in prev_close and prev_close[s] > 0):
            continue
        elig.append(i)
        gap = (sess_open[s] - prev_close[s]) / prev_close[s]
        if gap > gap_k and c[i] > sess_open[s] and c[i] > vwap[i]:
            entry[i] = True
    return {"entry": entry, "eligible": elig}


# ── 4. ATR 압축 돌파 ──────────────────────────────────────────────────────────
def atr_compression(ohlc, feat, aux, params):
    h, l, c = ohlc["high"], ohlc["low"], ohlc["close"]
    mso, atr = feat["mso"], feat["atr_abs"]
    ap = atr_pct(h, l, c, 14)
    N = params.get("breakout_lookback", 20); M = params.get("atr_window", 50)
    ratio = params.get("squeeze_ratio", 0.7); orm = params.get("or_minutes", 30)
    n = len(c); entry = [False] * n; elig = []
    for i in range(n):
        if not (mso[i] >= orm and atr[i] and ap[i] is not None and i >= max(N, M)):
            continue
        elig.append(i)
        recent = [x for x in ap[i - M:i] if x is not None]
        if not recent:
            continue
        squeeze = ap[i] < ratio * (sum(recent) / len(recent))
        breakout = c[i] > max(h[i - N:i])
        if squeeze and breakout:
            entry[i] = True
    return {"entry": entry, "eligible": elig}


# ── 5. 섹터상대 모멘텀 (stock > sector ETF > SPY) ─────────────────────────────
def sector_aux(symbol: str, ohlc: dict) -> dict:
    etf = SECTOR_MAP.get(symbol)
    spy = load_ohlc_lists("SPY", INTRADAY_TF)
    sec = load_ohlc_lists(etf, INTRADAY_TF) if etf else {"ts": [], "close": []}
    spy_map = dict(zip(spy["ts"], spy["close"]))
    sec_map = dict(zip(sec["ts"], sec["close"]))
    return {
        "spy_close": [spy_map.get(t) for t in ohlc["ts"]],
        "sec_close": [sec_map.get(t) for t in ohlc["ts"]],
    }


def sector_relative_momentum(ohlc, feat, aux, params):
    c = ohlc["close"]; vwap, mso, sids, atr = feat["vwap"], feat["mso"], feat["sids"], feat["atr_abs"]
    spy_c = aux.get("spy_close"); sec_c = aux.get("sec_close")
    n = len(c); entry = [False] * n; elig = []
    if not spy_c or not sec_c:
        return {"entry": entry, "eligible": elig}
    ema20 = _ema(c, 20)
    rvolv = _rvol(ohlc["volume"], sids, mso)
    rv_min = params.get("rvol_min", 1.2); orm = params.get("or_minutes", 30)
    sess_open = {}; spy_open = {}; sec_open = {}
    for i in range(n):
        s = sids[i]
        if s not in sess_open:
            sess_open[s] = c[i]
            if spy_c[i]:
                spy_open[s] = spy_c[i]
            if sec_c[i]:
                sec_open[s] = sec_c[i]
    for i in range(n):
        s = sids[i]
        if not (mso[i] >= orm and vwap[i] and atr[i] and ema20[i] is not None
                and i > 0 and ema20[i - 1] is not None and spy_c[i] and sec_c[i]
                and rvolv[i] is not None and s in spy_open and s in sec_open and sess_open[s] > 0):
            continue
        elig.append(i)
        stock_mom = c[i] / sess_open[s] - 1
        spy_mom = spy_c[i] / spy_open[s] - 1
        sec_mom = sec_c[i] / sec_open[s] - 1
        if stock_mom > sec_mom > spy_mom and c[i] > vwap[i] and rvolv[i] > rv_min and ema20[i] > ema20[i - 1]:
            entry[i] = True
    return {"entry": entry, "eligible": elig}
