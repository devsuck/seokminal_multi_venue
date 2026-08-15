"""옵션 UOA 사후수익률 라벨링 규약 테스트.

핵심은 lookahead 방지(탐지 다음 거래일 시가 진입)와 pseudo-replication 방지
(같은 티커·같은 날 계약 여러 개 = 관측 1건). 둘 다 틀리면 없는 엣지가 보인다.
"""
from __future__ import annotations

import pytest

from research.run_options_uoa_forward import forward_return, group_signals, summarize

# 4 거래일: 진입 후보는 인덱스 1부터
_BARS = {
    "dates": ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"],
    "open":  [100.0, 100.0, 110.0, 120.0],
    "close": [100.0, 105.0, 115.0, 130.0],
}


def _event(ticker="INTC", detected="2026-08-03T22:00:00+00:00", type_="call", ratio=10.0):
    return {"ticker": ticker, "detected_at": detected, "type": type_, "vol_oi_ratio": ratio,
            "volume": 100, "dte": 1, "moneyness_pct": 5.0}


def test_forward_return_enters_next_session_open():
    # 08-03 탐지 → 08-04 시가 100 진입, 1일 보유 → 08-05 종가 115
    assert forward_return(_BARS, "2026-08-03", hold=1, side="call") == pytest.approx(0.15)


def test_put_signal_is_short_direction():
    assert forward_return(_BARS, "2026-08-03", hold=1, side="put") == pytest.approx(-0.15)


def test_returns_none_when_future_bars_missing():
    # 마지막 바 근처 → 보유기간이 아직 안 지남
    assert forward_return(_BARS, "2026-08-05", hold=1, side="call") is None
    assert forward_return(_BARS, "2026-08-06", hold=1, side="call") is None


def test_same_ticker_day_collapses_to_one_signal():
    events = [_event(ratio=10.0), _event(ratio=99.0), _event(ratio=5.0)]
    signals = group_signals(events)
    assert len(signals) == 1
    assert signals[0]["n_contracts"] == 3
    assert signals[0]["max_vol_oi"] == 99.0


def test_call_and_put_stay_separate_signals():
    signals = group_signals([_event(type_="call"), _event(type_="put")])
    assert {s["side"] for s in signals} == {"call", "put"}   # 방향 반대 — 합치면 상쇄됨


def test_summarize_ignores_unlabeled_rows():
    labeled = [{"fwd_1d": 0.1}, {"fwd_1d": -0.3}, {"fwd_1d": None}]
    s = summarize(labeled)["fwd_1d"]
    assert s["n"] == 2 and s["win_rate"] == 0.5
    assert summarize([{"fwd_1d": None}])["fwd_1d"]["n"] == 0     # 전부 미래면 0건
