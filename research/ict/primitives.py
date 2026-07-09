"""ICT 객관 프리미티브 — 봉 배열 입력, 인덱스 기반 이벤트 반환.

봉 = dict{ts,o,h,l,c} 병렬 리스트. 모든 정의는 **명시적·재현가능**(사후 선택 없음).
포함(객관): FVG · order block · liquidity sweep · swing · market structure(BOS/CHoCH) ·
             kill zone(시간) · OTE(피보) · unicorn(OB∩FVG) · iFVG(역전) · CISD(배송전환) ·
             turtle soup(구조적 스윙 가짜돌파 반전).
제외(주관·검증불가): draw-on-liquidity, MMxM 시퀀싱, weekly profile, judas '의도'.

ICT 실전은 이 프리미티브들을 여러 개 동시에 AND결합해서 씀(단일 개념만으론 안 씀) —
research/ict/combinator.py의 evaluate_combo()가 임의 부분집합을 AND결합.
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


# ── OTE 존 터치 이벤트화 (직전 BOS 리그 되돌림) ──────────────
def ote_touches(h: list[float], l: list[float], c: list[float], k: int = 2, window: int = 8) -> list[dict]:
    """market_structure BOS 직후 그 리그의 62-79% 되돌림존을 window봉 내 터치 → 이벤트."""
    ms = market_structure(h, l, c, k)
    sw = swings(h, l, k)
    highs, lows = sw["highs"], sw["lows"]
    n = len(c)
    out = []
    for e in ms:
        i, direction = e["idx"], e["dir"]
        if direction == "bullish":
            prior = [x for x in lows if x < i]
            if not prior:
                continue
            leg_lo, leg_hi = l[prior[-1]], h[i]
            if leg_hi <= leg_lo:
                continue
            zlo, zhi = ote_zone(leg_lo, leg_hi, "bullish")
            for j in range(i + 1, min(i + 1 + window, n)):
                if zlo <= l[j] <= zhi:
                    out.append({"idx": j, "type": "bullish"}); break
        else:
            prior = [x for x in highs if x < i]
            if not prior:
                continue
            leg_hi, leg_lo = h[prior[-1]], l[i]
            if leg_hi <= leg_lo:
                continue
            zlo, zhi = ote_zone(leg_lo, leg_hi, "bearish")
            for j in range(i + 1, min(i + 1 + window, n)):
                if zlo <= h[j] <= zhi:
                    out.append({"idx": j, "type": "bearish"}); break
    return out


# ── Unicorn (order block ∩ fair value gap 컨플루언스) ────────
def unicorn_zones(o: list[float], h: list[float], l: list[float], c: list[float], near: int = 3) -> list[dict]:
    """같은 방향 OB 존과 FVG 존이 근접(±near봉)+가격구간 겹침 → 컨플루언스 이벤트(FVG idx에 표시)."""
    obs = order_blocks(o, h, l, c)
    fvgs = fair_value_gaps(h, l)
    out = []
    for f in fvgs:
        for ob in obs:
            if ob["type"] != f["type"] or abs(ob["idx"] - f["idx"]) > near:
                continue
            if f["gap_hi"] < ob["zone_lo"] or f["gap_lo"] > ob["zone_hi"]:
                continue
            out.append({"idx": f["idx"], "type": f["type"]})
            break
    return out


# ── iFVG (반대방향 FVG를 종가로 관통 = 역전, 되돌림 시 지지/저항) ──
def ifvg_events(h: list[float], l: list[float], c: list[float], window: int = 8) -> list[dict]:
    """bearish FVG 상방관통(bullish 역전) / bullish FVG 하방관통(bearish 역전) 후
    window봉 내 그 구간 되돌림 = 진입 이벤트."""
    fvgs = fair_value_gaps(h, l)
    n = len(c)
    out = []
    for f in fvgs:
        i = f["idx"]
        if f["type"] == "bearish":
            viol = next((j for j in range(i + 1, min(i + 1 + window, n)) if c[j] > f["gap_hi"]), None)
            if viol is None:
                continue
            hit = next((k for k in range(viol + 1, min(viol + 1 + window, n)) if l[k] <= f["gap_hi"]), None)
            if hit is not None:
                out.append({"idx": hit, "type": "bullish"})
        else:
            viol = next((j for j in range(i + 1, min(i + 1 + window, n)) if c[j] < f["gap_lo"]), None)
            if viol is None:
                continue
            hit = next((k for k in range(viol + 1, min(viol + 1 + window, n)) if h[k] >= f["gap_lo"]), None)
            if hit is not None:
                out.append({"idx": hit, "type": "bearish"})
    return out


# ── CISD (Change in State of Delivery: 연속 반대캔들열 첫시가 관통) ──
def cisd_events(o: list[float], h: list[float], l: list[float], c: list[float], min_run: int = 2) -> list[dict]:
    """연속 하락(상승)캔들열의 첫 시가를 종가로 반대방향 관통 = 배송방향 전환."""
    out = []
    for i in range(min_run + 1, len(c)):
        j = i - 1
        down_run = 0
        while j >= 0 and c[j] < o[j]:
            down_run += 1; j -= 1
        if down_run >= min_run and c[i] > o[j + 1]:
            out.append({"idx": i, "type": "bullish"})
            continue
        j = i - 1
        up_run = 0
        while j >= 0 and c[j] > o[j]:
            up_run += 1; j -= 1
        if up_run >= min_run and c[i] < o[j + 1]:
            out.append({"idx": i, "type": "bearish"})
    return out


# ── Turtle Soup (확정 swing high/low 가짜돌파 후 반전) ───────
def turtle_soup_events(h: list[float], l: list[float], c: list[float], k: int = 2, confirm: int = 3) -> list[dict]:
    """확정 swing low/high를 살짝 하회/상회(가짜돌파) 후 confirm봉 내 종가가 그 레벨 원위치 복귀 = 반전."""
    sw = swings(h, l, k)
    n = len(c)
    out = []
    for s in sw["lows"]:
        level = l[s]
        for i in range(s + 1, min(s + 1 + confirm + 5, n)):
            if l[i] < level:
                hit = next((j for j in range(i, min(i + confirm, n)) if c[j] > level), None)
                if hit is not None:
                    out.append({"idx": hit, "type": "bullish"})
                break
    for s in sw["highs"]:
        level = h[s]
        for i in range(s + 1, min(s + 1 + confirm + 5, n)):
            if h[i] > level:
                hit = next((j for j in range(i, min(i + confirm, n)) if c[j] < level), None)
                if hit is not None:
                    out.append({"idx": hit, "type": "bearish"})
                break
    return out
