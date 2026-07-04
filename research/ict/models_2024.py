"""ICT 2024 멘토십 모델들 — 객관 기계화(공개 개념, 영상 복제 아님).

각 모델 = 진입 인덱스 리스트 반환. 프리미티브 조합. 당일청산 단타.
포함: 2024 model(sweep→변위FVG→되돌림) · OTE(피보 62-79) · Unicorn(OB+FVG) · Silver Bullet(좁은 킬존).
주관 개념(draw-on-liquidity 등)은 제외. 정직.
"""
from __future__ import annotations

from research.ict.primitives import (
    fair_value_gaps,
    killzone_indices,
    liquidity_sweeps,
    market_structure,
    order_blocks,
    ote_zone,
    swings,
)


def _kz_set(ts, kz):
    return set(killzone_indices(ts, kz[0], kz[1]))


def model_2024(bars, kz=(13.5, 15.0), lb=10, look=6):
    """유동성 sweep → 상방 변위(bullish FVG) → FVG 되돌림 진입."""
    h, l, c, ts = bars["h"], bars["l"], bars["c"], bars["ts"]
    n = len(c)
    fvgs = [f for f in fair_value_gaps(h, l) if f["type"] == "bullish"]
    sweeps = {s["idx"] for s in liquidity_sweeps(h, l, c, lb) if s["type"] == "bullish"}
    kzs = _kz_set(ts, kz)
    ent = []
    for f in fvgs:
        i = f["idx"]
        if i not in kzs:
            continue
        if not any((i - 3) <= s <= i for s in sweeps):   # 최근 sweep
            continue
        for j in range(i + 1, min(i + 1 + look, n - 1)):   # FVG 되돌림
            if l[j] <= f["gap_hi"]:
                ent.append(j); break
    return ent


def model_silver_bullet(bars, lb=10, look=4):
    """NY 10-11am(≈14:00-15:00 UTC EDT) 좁은 킬존, sweep 후 첫 bullish FVG 되돌림."""
    return model_2024(bars, kz=(14.0, 15.0), lb=lb, look=look)


def model_ote(bars, k=2, look=8, kz=(13.5, 15.0)):
    """상방 BOS(변위) → 직전 스윙저-고 62-79% 되돌림 진입."""
    h, l, c, ts = bars["h"], bars["l"], bars["c"], bars["ts"]
    n = len(c)
    kzs = _kz_set(ts, kz)
    ms = [e for e in market_structure(h, l, c, k) if e["dir"] == "bullish"]
    sw = swings(h, l, k)
    lows = sw["lows"]
    ent = []
    for e in ms:
        i = e["idx"]
        if i not in kzs:
            continue
        prior_lows = [x for x in lows if x < i]
        if not prior_lows:
            continue
        leg_lo = l[prior_lows[-1]]; leg_hi = h[i]
        if leg_hi <= leg_lo:
            continue
        zlo, zhi = ote_zone(leg_lo, leg_hi, "bullish")
        for j in range(i + 1, min(i + 1 + look, n - 1)):   # OTE 존 되돌림
            if zlo <= l[j] <= zhi:
                ent.append(j); break
    return ent


def model_unicorn(bars, kz=(13.5, 15.0)):
    """bullish order block 존 ∩ bullish FVG 존 겹침 → 진입."""
    h, l, c, ts = bars["h"], bars["l"], bars["c"], bars["ts"]
    kzs = _kz_set(ts, kz)
    obs = [o for o in order_blocks(bars["o"], h, l, c) if o["type"] == "bullish"]
    fvgs = [f for f in fair_value_gaps(h, l) if f["type"] == "bullish"]
    ent = []
    for f in fvgs:
        i = f["idx"]
        if i not in kzs:
            continue
        # 근처(±3) OB와 가격존 겹침
        for o in obs:
            if abs(o["idx"] - i) <= 3 and not (f["gap_hi"] < o["zone_lo"] or f["gap_lo"] > o["zone_hi"]):
                ent.append(i); break
    return ent


def model_ifvg(bars, kz=(13.5, 15.0), look=8):
    """iFVG: bearish FVG를 종가로 상방 관통(inversion) → 되돌림 시 지지 진입."""
    h, l, c, ts = bars["h"], bars["l"], bars["c"], bars["ts"]
    n = len(c)
    bear = [f for f in fair_value_gaps(h, l) if f["type"] == "bearish"]
    kzs = _kz_set(ts, kz)
    ent = []
    for f in bear:
        i = f["idx"]
        viol = None
        for j in range(i + 1, min(i + 1 + look, n)):   # 종가 상방 관통 = 반전
            if c[j] > f["gap_hi"]:
                viol = j; break
        if viol is None:
            continue
        for k in range(viol + 1, min(viol + 1 + look, n - 1)):   # 반전레벨 되돌림
            if k in kzs and l[k] <= f["gap_hi"]:
                ent.append(k); break
    return ent


def model_cisd(bars, kz=(13.5, 15.0), min_run=2):
    """CISD: 연속 하락캔들열의 첫 시가를 종가로 상방 관통 = 배송방향 전환."""
    o, h, l, c, ts = bars["o"], bars["h"], bars["l"], bars["c"], bars["ts"]
    kzs = _kz_set(ts, kz)
    ent = []
    for i in range(min_run + 1, len(c)):
        run = 0
        j = i - 1
        while j >= 0 and c[j] < o[j]:   # 하락캔들 연속
            run += 1; j -= 1
        if run >= min_run:
            first_open = o[j + 1]        # 하락열 첫 캔들 시가
            if c[i] > first_open and i in kzs:
                ent.append(i)
    return ent


MODELS = {
    "ict2024_model": model_2024,
    "ict_silver_bullet": model_silver_bullet,
    "ict_ote": model_ote,
    "ict_unicorn": model_unicorn,
    "ict_ifvg": model_ifvg,
    "ict_cisd": model_cisd,
}
