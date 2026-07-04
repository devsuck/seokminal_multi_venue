"""ICT 객관 프리미티브 — 봉 배열 입력, 인덱스 기반 이벤트 반환.

봉 = dict{ts,o,h,l,c} 병렬 리스트. 모든 정의는 **명시적·재현가능**(사후 선택 없음).
포함(객관): FVG · order block · liquidity sweep · swing · market structure(BOS/CHoCH) ·
             kill zone(시간) · OTE(피보).
제외(주관·검증불가): draw-on-liquidity, MMxM 시퀀싱, weekly profile, judas '의도'.
"""
from __future__ import annotations

import datetime as _dt


# ── Fair Value Gap (3봉 불균형) ──────────────────────────────
def fair_value_gaps(h: list[float], l: list[float]) -> list[dict]:
    """FVG: bullish = l[i] > h[i-2](위로 갭), bearish = h[i] < l[i-2](아래 갭). i에 표시."""
    out = []
    for i in range(2, len(h)):
        if l[i] > h[i - 2]:
            out.append({"idx": i, "type": "bullish", "gap_lo": h[i - 2], "gap_hi": l[i]})
        elif h[i] < l[i - 2]:
            out.append({"idx": i, "type": "bearish", "gap_lo": h[i], "gap_hi": l[i - 2]})
    return out


def has_bullish_fvg_near(fvgs: list[dict], i: int, window: int = 1) -> bool:
    return any(f["type"] == "bullish" and i - window <= f["idx"] <= i for f in fvgs)


# ── Order Block (변위 직전 반대봉) ───────────────────────────
def order_blocks(o: list[float], h: list[float], l: list[float], c: list[float]) -> list[dict]:
    """bullish OB = 하락봉[i] 직후 봉[i+1]이 OB 고가 돌파(변위up). 객관 규칙."""
    out = []
    for i in range(len(c) - 1):
        down = c[i] < o[i]
        up = c[i] > o[i]
        if down and c[i + 1] > h[i]:      # 하락봉 뒤 상방 변위
            out.append({"idx": i, "type": "bullish", "zone_lo": l[i], "zone_hi": h[i]})
        elif up and c[i + 1] < l[i]:       # 상승봉 뒤 하방 변위
            out.append({"idx": i, "type": "bearish", "zone_lo": l[i], "zone_hi": h[i]})
    return out


# ── Liquidity Sweep (유동성 사냥) ────────────────────────────
def liquidity_sweeps(h: list[float], l: list[float], c: list[float], lookback: int = 10) -> list[dict]:
    """bullish sweep = 직전 lookback 최저 하회(꼬리) 후 그 위로 종가 회복(매도측 유동성 사냥)."""
    out = []
    for i in range(lookback, len(l)):
        prior_lo = min(l[i - lookback:i])
        prior_hi = max(h[i - lookback:i])
        if l[i] < prior_lo and c[i] > prior_lo:
            out.append({"idx": i, "type": "bullish", "swept": prior_lo})
        elif h[i] > prior_hi and c[i] < prior_hi:
            out.append({"idx": i, "type": "bearish", "swept": prior_hi})
    return out


def is_bullish_sweep(sweeps: list[dict], i: int) -> bool:
    return any(s["idx"] == i and s["type"] == "bullish" for s in sweeps)


# ── Swing points (프랙탈) ────────────────────────────────────
def swings(h: list[float], l: list[float], k: int = 2) -> dict:
    """swing high = h[i]가 좌우 k봉보다 크다. swing low = l[i]가 좌우 k봉보다 작다."""
    highs, lows = [], []
    for i in range(k, len(h) - k):
        win_h = h[i - k:i + k + 1]
        win_l = l[i - k:i + k + 1]
        if h[i] == max(win_h) and win_h.count(h[i]) == 1:
            highs.append(i)
        if l[i] == min(win_l) and win_l.count(l[i]) == 1:
            lows.append(i)
    return {"highs": highs, "lows": lows}


# ── Market structure (BOS / CHoCH) ──────────────────────────
def market_structure(h: list[float], l: list[float], c: list[float], k: int = 2) -> list[dict]:
    """확정 swing 대비 종가 돌파 → BOS(추세지속)/CHoCH(성격전환). 객관."""
    sw = swings(h, l, k)
    events = []
    last_sh = None   # 최근 확정 swing high 값
    last_sl = None
    trend = 0        # +1 up, -1 down, 0 none
    sh_set = {i: h[i] for i in sw["highs"]}
    sl_set = {i: l[i] for i in sw["lows"]}
    for i in range(len(c)):
        if i in sh_set:
            last_sh = sh_set[i]
        if i in sl_set:
            last_sl = sl_set[i]
        if last_sh is not None and c[i] > last_sh:
            kind = "BOS" if trend >= 0 else "CHoCH"
            events.append({"idx": i, "dir": "bullish", "kind": kind, "level": last_sh})
            trend = 1; last_sh = None
        elif last_sl is not None and c[i] < last_sl:
            kind = "BOS" if trend <= 0 else "CHoCH"
            events.append({"idx": i, "dir": "bearish", "kind": kind, "level": last_sl})
            trend = -1; last_sl = None
    return events


# ── Kill zone (시간창; ts_utc epoch sec → UTC 시각) ──────────
# NY 오픈 킬존 ≈ 13:30–15:00 UTC(EDT 9:30–11:00). DST 근사(UTC 고정창).
def in_killzone(ts_utc: int, start_hour: float = 13.5, end_hour: float = 15.0) -> bool:
    t = _dt.datetime.fromtimestamp(int(ts_utc), tz=_dt.timezone.utc)
    hf = t.hour + t.minute / 60.0
    return start_hour <= hf < end_hour


def killzone_indices(ts: list[int], start_hour: float = 13.5, end_hour: float = 15.0) -> list[int]:
    return [i for i, t in enumerate(ts) if in_killzone(t, start_hour, end_hour)]


# ── OTE (Optimal Trade Entry, 62–79% 되돌림) ────────────────
def ote_zone(swing_low: float, swing_high: float, direction: str = "bullish") -> tuple[float, float]:
    """bullish: 상승(low→high)의 62–79% 되돌림 매수구간 반환 (하단, 상단)."""
    rng = swing_high - swing_low
    if direction == "bullish":
        return (swing_high - 0.79 * rng, swing_high - 0.62 * rng)
    return (swing_low + 0.62 * rng, swing_low + 0.79 * rng)


def in_ote(price: float, zone: tuple[float, float]) -> bool:
    return zone[0] <= price <= zone[1]
