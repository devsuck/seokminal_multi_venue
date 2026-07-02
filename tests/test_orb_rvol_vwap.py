"""ORB+RVOL+VWAP dormant 모듈 테스트 — 실데이터 없이 synthetic fixture로."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

import research.data.intraday_store as store
from research.features.session import session_ids, minutes_since_open
from research.features.opening_range import opening_range
from research.features.vwap import session_vwap
from research.features.rvol import rvol as compute_rvol
from research.backtest.event_backtester import run_event_backtest
from research.strategies.orb_rvol_vwap import (
    run_hypothesis, generate_signals, IntradayDataRequiredError, DEFAULTS,
)

ET = ZoneInfo("America/New_York")


def _session_ts(day: dt.date, n_bars: int, step_min: int = 15) -> list[int]:
    """ET 09:30부터 step_min 간격 n_bars개의 UTC epoch."""
    open_et = dt.datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)
    return [int((open_et + dt.timedelta(minutes=step_min * i)).timestamp()) for i in range(n_bars)]


def _make_sessions(n_sessions: int, bars_per: int = 26):
    """상승 브레이크아웃이 있는 synthetic 15m 세션들."""
    ts, o, h, l, c, v = [], [], [], [], [], []
    day = dt.date(2025, 3, 3)  # 월요일
    made = 0
    while made < n_sessions:
        if day.weekday() < 5:  # 평일만
            sts = _session_ts(day, bars_per)
            base = 100.0
            for i, t in enumerate(sts):
                # OR(첫 2봉) 좁게, 이후 상승 브레이크아웃
                px = base + (0.0 if i < 2 else 0.3 * (i - 1))
                ts.append(t); o.append(px); c.append(px + 0.1)
                h.append(px + 0.2); l.append(px - 0.2)
                v.append(1000.0 + (500.0 if i == 5 else 0.0))  # 6번째 봉 볼륨 급증
            made += 1
        day += dt.timedelta(days=1)
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_session_grouping_and_minutes():
    ts = _session_ts(dt.date(2025, 3, 3), 4)
    sids = session_ids(ts)
    assert len(set(sids)) == 1  # 한 세션
    mso = minutes_since_open(ts, sids)
    assert mso == [0.0, 15.0, 30.0, 45.0]


def test_opening_range_first_30min():
    ts = _session_ts(dt.date(2025, 3, 3), 6)
    sids = session_ids(ts)
    mso = minutes_since_open(ts, sids)
    highs = [10, 12, 20, 21, 22, 23]
    lows = [9, 8, 15, 16, 17, 18]
    orr = opening_range(highs, lows, sids, mso, or_minutes=30)
    # 첫 30분 = 0,15분 봉(2개) → OR high=max(10,12)=12, low=min(9,8)=8
    assert orr["or_high"][0] == 12 and orr["or_low"][0] == 8
    assert orr["in_or_window"][0] is True and orr["in_or_window"][2] is False


def test_vwap_resets_per_session():
    ts = _session_ts(dt.date(2025, 3, 3), 2) + _session_ts(dt.date(2025, 3, 4), 2)
    sids = session_ids(ts)
    h = [10, 10, 20, 20]; l = [10, 10, 20, 20]; c = [10, 10, 20, 20]; vol = [1, 1, 1, 1]
    vw = session_vwap(h, l, c, vol, sids)
    assert vw[0] == 10 and vw[1] == 10        # 1세션
    assert vw[2] == 20 and vw[3] == 20        # 2세션 리셋


def test_rvol_warmup_then_ratio():
    # 같은 슬롯 반복 → 워밍업 후 비율 나옴
    vols = [100.0] * 6 + [300.0]
    sids = [f"d{i}" for i in range(7)]
    mso = [0.0] * 7  # 전부 같은 슬롯
    rv = compute_rvol(vols, sids, mso, lookback_sessions=20, min_sessions=5)
    assert rv[0] is None and rv[4] is None    # 워밍업(<5)
    assert rv[5] == pytest.approx(1.0)        # 100/평균100
    assert rv[6] == pytest.approx(3.0)        # 300/평균100


def test_event_backtest_target_stop_timestop():
    closes = [100, 100, 100, 100, 100, 100]
    highs = [100, 100, 112, 100, 100, 100]   # idx2에서 target(+10) 초과
    lows = [100, 100, 100, 100, 100, 100]
    atr = [5.0] * 6
    sig = [False, True, False, False, False, False]  # idx1 진입
    tr = run_event_backtest(highs, lows, closes, sig, atr, trade_size=1, cost_bps=0,
                            stop_atr=1.0, target_atr=2.0, time_stop_bars=8)
    assert len(tr) == 1 and tr[0]["exit_reason"] == "target"

    lows2 = [100, 100, 94, 100, 100, 100]     # idx2에서 stop(-5) 이탈
    highs2 = [100, 100, 100, 100, 100, 100]
    tr2 = run_event_backtest(highs2, lows2, closes, sig, atr, trade_size=1, cost_bps=0)
    assert tr2[0]["exit_reason"] == "stop"

    flat_h = [100] * 6; flat_l = [100] * 6
    tr3 = run_event_backtest(flat_h, flat_l, closes, sig, atr, trade_size=1, cost_bps=0,
                             time_stop_bars=2)
    assert tr3[0]["exit_reason"] == "time_stop"


def test_daily_tf_raises():
    with pytest.raises(IntradayDataRequiredError):
        run_hypothesis("AAPL", tf="1d", write_report=False)


def test_missing_data_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    res = run_hypothesis("NOPE", tf="15m", write_report=False)
    assert res["blocked"] is True and "intraday" in res["reason"].lower()


def test_full_run_on_synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path))
    data = _make_sessions(10)
    rows = [{"ts_utc": data["ts"][i], "open": data["open"][i], "high": data["high"][i],
             "low": data["low"][i], "close": data["close"][i], "volume": data["volume"][i]}
            for i in range(len(data["ts"]))]
    store.save_bars("SYNTH", "15m", rows)
    res = run_hypothesis("SYNTH", tf="15m", n_runs=100, seed=1, cost_bps=5, write_report=False)
    assert res["blocked"] is False
    assert "num_trades" in res["strategy"]
    assert "percentile" in res["random"] and res["random"]["n_random"] == 100
    assert res["eligible_count"] >= 0
