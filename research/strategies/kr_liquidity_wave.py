"""KR Liquidity Wave Pullback v1 — 공개 데이터 유동성 파동 검증 (조작 탐지 아님).

용어: liquidity_impulse / pullback / rebreakout_confirmation. '세력' 코드에 안 씀.
로직: 비정상 유동성/가격 임펄스 → 통제된 눌림(거래대금 수축) → 거래대금 동반 재돌파 →
      다음날 시가 진입 → 눌림저점 이탈 or 10일 타임스탑 청산. 고정 파라미터·미최적화.
"""
from __future__ import annotations

import statistics as _st

DEFAULTS = {
    "impulse_ret": 0.10,        # 임펄스일 등락 >= +10%
    "impulse_tval_mult": 5.0,   # 거래대금 >= 5 * avg20
    "pullback_min": 2,          # 임펄스 후 2~10일 관찰
    "pullback_max": 10,
    "max_drop_from_high": 0.25, # 임펄스 고점 대비 25% 초과 하락 = 무효
    "rebreak_tval_mult": 2.0,   # 재돌파 거래대금 >= 2 * avg5
    "time_stop": 10,
}


def generate_trades(bars: list[dict], params: dict | None = None) -> list[dict]:
    """단일 종목 bars(date/open/high/low/close/tval) → 트레이드.
    반환: [{event_date, entry_idx, exit_idx, entry_price, exit_price, ret, reason}]."""
    p = {**DEFAULTS, **(params or {})}
    n = len(bars)
    o = [b["open"] for b in bars]; h = [b["high"] for b in bars]
    l = [b["low"] for b in bars]; c = [b["close"] for b in bars]
    tv = [b["tval"] for b in bars]
    trades = []
    i = 20
    while i < n - p["pullback_min"] - 2:
        avg20 = _st.mean(tv[i - 20:i]) if i >= 20 else 0
        ret = (c[i] / c[i - 1] - 1) if c[i - 1] > 0 else 0
        # 1. 유동성 임펄스
        if not (ret >= p["impulse_ret"] and avg20 > 0 and tv[i] >= p["impulse_tval_mult"] * avg20):
            i += 1; continue
        base_low, imp_high, imp_tval = l[i], h[i], tv[i]
        pb_high, pb_low = h[i + 1], l[i + 1]
        done = False
        # 2~3. 눌림 관찰 + 재돌파
        for k in range(i + p["pullback_min"], min(i + p["pullback_max"] + 1, n)):
            if l[k] < base_low or l[k] < imp_high * (1 - p["max_drop_from_high"]):
                break  # 임펄스 저점 이탈 or 25%+ 하락 → 무효
            avg5 = _st.mean(tv[k - 5:k]) if k >= 5 else tv[k]
            pb_tvals = tv[i + 1:k]
            vol_contract = pb_tvals and _st.mean(pb_tvals) < imp_tval
            if c[k] > pb_high and avg5 > 0 and tv[k] >= p["rebreak_tval_mult"] * avg5 and vol_contract:
                # 4. 다음날 시가 진입
                ei = k + 1
                if ei >= n:
                    break
                entry = o[ei]
                if entry <= 0:
                    break
                # 5. 청산: 종가 < 눌림저점 or 타임스탑
                xi, reason = min(ei + p["time_stop"], n - 1), "time_stop"
                for m in range(ei, min(ei + p["time_stop"] + 1, n)):
                    if c[m] < pb_low:
                        xi, reason = m, "stop"; break
                trades.append({"event_date": bars[i]["date"], "entry_idx": ei, "exit_idx": xi,
                               "entry_price": entry, "exit_price": c[xi],
                               "ret": round(c[xi] / entry - 1, 6), "reason": reason})
                done = True
                i = xi + 1  # 청산 후부터
                break
            pb_high = max(pb_high, h[k]); pb_low = min(pb_low, l[k])
        if not done:
            i += 1
    return trades


def liquidity_bucket(amount: float) -> str:
    """거래대금 버킷 (random 매칭용)."""
    if amount >= 5e10:
        return "high"
    if amount >= 1.5e10:
        return "mid"
    return "low"
