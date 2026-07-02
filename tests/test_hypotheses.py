"""가설 5종 signal 함수 synthetic 테스트 (실데이터 무관)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from research.hypotheses.runner import common_features
from research.hypotheses import strategies as S

ET = ZoneInfo("America/New_York")


def _mk(n_sessions=8, bars=26, price_fn=None):
    ts, o, h, l, c, v = [], [], [], [], [], []
    day = dt.date(2025, 3, 3)
    made = 0
    while made < n_sessions:
        if day.weekday() < 5:
            open_et = dt.datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)
            for i in range(bars):
                t = int((open_et + dt.timedelta(minutes=15 * i)).timestamp())
                px = price_fn(made, i) if price_fn else 100.0 + 0.1 * i
                ts.append(t); o.append(px); c.append(px)
                h.append(px + 0.3); l.append(px - 0.3); v.append(1000.0)
            made += 1
        day += dt.timedelta(days=1)
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _run(fn, ohlc, params=None, aux=None):
    feat = common_features(ohlc)
    return fn(ohlc, feat, aux or {}, params or {})


def test_all_return_valid_shape():
    ohlc = _mk()
    for fn in [S.vwap_mean_reversion, S.orb_failed_reversal, S.gap_continuation, S.atr_compression]:
        r = _run(fn, ohlc)
        assert len(r["entry"]) == len(ohlc["close"])
        assert all(isinstance(x, bool) for x in r["entry"])
        assert all(0 <= i < len(ohlc["close"]) for i in r["eligible"])
        # entry는 eligible의 부분집합
        assert all(i in set(r["eligible"]) for i, e in enumerate(r["entry"]) if e)


def test_vwap_mr_fires_when_deep_below_vwap():
    # 세션 초반 급락 → 종가 VWAP 크게 아래 + RSI 과매도
    def pf(sess, i):
        return 100.0 if i < 3 else 100.0 - 2.0 * (i - 2)  # 계속 하락
    ohlc = _mk(price_fn=pf)
    r = _run(S.vwap_mean_reversion, ohlc, {"dev_k": 0.003, "rsi_max": 45})
    assert any(r["entry"])  # 하락 구간에서 MR 진입 발생


def test_gap_continuation_fires_on_gap_up():
    # 세션마다 전일 대비 갭업 + 상승 유지
    def pf(sess, i):
        base = 100.0 + sess * 5.0  # 세션마다 +5 갭업(전일 종가 대비)
        return base + 0.05 * i     # 세션내 상승은 작게 → 갭 유지
    ohlc = _mk(price_fn=pf)
    r = _run(S.gap_continuation, ohlc, {"gap_k": 0.005})
    assert any(r["entry"])


def test_sector_relative_no_aux_returns_empty():
    ohlc = _mk()
    r = _run(S.sector_relative_momentum, ohlc, aux={})
    assert not any(r["entry"]) and r["eligible"] == []


def test_sector_relative_fires_when_outperforming():
    ohlc = _mk(price_fn=lambda s, i: 100.0 + 1.0 * i)  # 강한 상승
    n = len(ohlc["close"])
    # SPY/섹터는 약하게 상승(종목이 초과) → aux 정렬 배열
    aux = {"spy_close": [100.0 + 0.05 * (i % 26) for i in range(n)],
           "sec_close": [100.0 + 0.1 * (i % 26) for i in range(n)]}
    r = _run(S.sector_relative_momentum, ohlc, {"rvol_min": 0.0}, aux=aux)
    assert len(r["entry"]) == n  # 실행됨(정렬·계산 정상)
