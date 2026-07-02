"""Triple Barrier 라벨링 단위 테스트."""
from __future__ import annotations

from xgb_strategy.labeling import atr_pct, triple_barrier_labels


def test_atr_pct_warmup_none():
    closes = [100.0] * 10
    highs = [101.0] * 10
    lows = [99.0] * 10
    av = atr_pct(highs, lows, closes, period=14)
    assert all(v is None for v in av)  # 데이터 부족 → 전부 None


def test_atr_pct_positive_after_warmup():
    n = 40
    closes = [100.0 + i for i in range(n)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    av = atr_pct(highs, lows, closes, period=14)
    assert av[13] is None            # warmup 경계
    assert av[14] is not None
    assert av[20] > 0                # ATR% 양수


def test_upper_barrier_hit_first_labels_1():
    # 인덱스 20에서 이후 급등 → 위 배리어 먼저 → 1
    n = 40
    closes = [100.0] * n
    highs = [100.5] * n
    lows = [99.5] * n
    # 21번 봉부터 크게 상승
    for j in range(21, n):
        closes[j] = 130.0
        highs[j] = 131.0
        lows[j] = 129.0
    labels = triple_barrier_labels(highs, lows, closes, up_mult=1.5, dn_mult=1.5, horizon=10, atr_period=14)
    assert labels[20] == 1


def test_lower_barrier_hit_first_labels_0():
    n = 40
    closes = [100.0] * n
    highs = [100.5] * n
    lows = [99.5] * n
    for j in range(21, n):  # 급락
        closes[j] = 70.0
        highs[j] = 71.0
        lows[j] = 69.0
    labels = triple_barrier_labels(highs, lows, closes, up_mult=1.5, dn_mult=1.5, horizon=10, atr_period=14)
    assert labels[20] == 0


def test_timeout_no_move_labels_0():
    # 변동 거의 없음 → horizon 내 배리어 미터치 → 0
    n = 60
    closes = [100.0 + (0.01 if i % 2 else -0.01) for i in range(n)]
    highs = [c + 0.02 for c in closes]
    lows = [c - 0.02 for c in closes]
    labels = triple_barrier_labels(highs, lows, closes, up_mult=3.0, dn_mult=3.0, horizon=5, atr_period=14)
    mid = [l for l in labels[20:40] if l is not None]
    assert mid and all(l == 0 for l in mid)


def test_tail_bars_unlabelable_none():
    n = 40
    closes = [100.0 + i * 0.1 for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    labels = triple_barrier_labels(highs, lows, closes, horizon=10, atr_period=14)
    # 마지막 horizon 봉은 라벨 불가 → None
    assert all(l is None for l in labels[n - 10 :])
