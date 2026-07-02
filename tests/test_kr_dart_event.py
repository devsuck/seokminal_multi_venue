"""KR DART 이벤트 스터디 로직 테스트 (데이터 무관)."""
from __future__ import annotations

import datetime as dt

from research.run_kr_dart_event_study import _fwd_return, _net, HOLD
from research.data.kr_dart_events import EVENT_DEFS


def _bars(n=40):
    d0 = dt.date(2024, 1, 1)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]
    return {"dates": dates, "open": [100.0 + i for i in range(n)], "close": [100.5 + i for i in range(n)]}


def test_fwd_return_next_day_entry_hold_exit():
    bars = _bars(40)
    ev = bars["dates"][5]                 # 공시일
    r = _fwd_return(bars, ev)
    # 진입 = 다음날(idx6) 시가 = 106, 청산 = idx(6+HOLD) 종가
    entry = bars["open"][6]
    xi = min(6 + HOLD, len(bars["dates"]) - 1)
    assert abs(r - (bars["close"][xi] / entry - 1)) < 1e-9


def test_fwd_return_none_when_event_after_last():
    bars = _bars(30)
    assert _fwd_return(bars, "2099-01-01") is None


def test_net_deducts_cost():
    assert _net(0.05, 40.0) == 0.05 - 40.0 / 10_000.0


def test_event_defs_bias_and_exclude():
    assert EVENT_DEFS["buyback"]["bias"] == "bullish"
    assert "처분" in EVENT_DEFS["buyback"]["exclude"]   # 처분(약세) 제외
    assert EVENT_DEFS["rights_issue"]["bias"] == "bearish"


def test_fwd_return_partial_hold_at_end():
    # 이벤트가 끝 근처 → HOLD 못 채워도 마지막 종가로 청산(None 아님)
    bars = _bars(40)
    ev = bars["dates"][30]
    r = _fwd_return(bars, ev)
    assert r is not None
