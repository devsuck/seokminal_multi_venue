"""Triple Barrier Labeling (Lopez de Prado 스타일).

단순 "다음 봉 오름?" 라벨은 노이즈가 큼. 대신 각 시점에서
 - 위 배리어(+up_mult × ATR) 먼저 닿으면 → 1 (매매가능한 상승)
 - 아래 배리어(−dn_mult × ATR) 먼저 닿으면 → 0
 - horizon 안에 둘 다 안 닿으면 → 0 (깨끗한 상승 아님, 롱온리 관점)
을 라벨로 삼음. 이게 실제 익절/손절 매매에 훨씬 가까움.
"""
from __future__ import annotations


def atr_pct(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """Wilder ATR을 종가 대비 비율(ATR/close)로 반환. warmup은 None."""
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < period + 1:
        return result

    trs: list[float] = [0.0] * n
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs[i] = max(hl, hc, lc)

    # 첫 ATR = TR[1..period] 평균, 이후 Wilder 평활
    atr = sum(trs[1 : period + 1]) / period
    if closes[period] > 0:
        result[period] = atr / closes[period]
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i]) / period
        if closes[i] > 0:
            result[i] = atr / closes[i]
    return result


def triple_barrier_labels(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    up_mult: float = 1.5,
    dn_mult: float = 1.5,
    horizon: int = 10,
    atr_period: int = 14,
) -> list[int | None]:
    """각 시점의 롱온리 3배리어 라벨(1/0) 또는 None(라벨 불가).

    None 반환 조건: ATR 미확정(warmup) 또는 앞으로 horizon 봉이 부족.
    동일 봉에서 양 배리어 동시 터치 → 보수적으로 0(하락 우선 가정, 봉내 순서 불명).
    """
    n = len(closes)
    labels: list[int | None] = [None] * n
    av = atr_pct(highs, lows, closes, atr_period)

    for i in range(n):
        vol = av[i]
        if vol is None or vol <= 0:
            continue
        if i + horizon >= n:  # 앞으로 완전한 horizon이 없으면 라벨 불가
            continue
        upper = closes[i] * (1.0 + up_mult * vol)
        lower = closes[i] * (1.0 - dn_mult * vol)
        label = 0  # 기본: 깨끗한 상승 없음
        for j in range(i + 1, i + horizon + 1):
            hit_up = highs[j] >= upper
            hit_dn = lows[j] <= lower
            if hit_dn:  # 하락 우선(동시 포함) → 0, 종료
                label = 0
                break
            if hit_up:  # 상승 먼저 → 1, 종료
                label = 1
                break
        labels[i] = label
    return labels
