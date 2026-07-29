"""P1.7 Strategy Return Matrix Layer 테스트.

검증: no-lookahead · 결정성 · 정렬 정확성 · 상관계산 일관성.
처리: 상이 보유기간 · 결측일 · 비활동 전략 · 겹침 포지션.
"""
from __future__ import annotations

from jarvis.fusion.backtest import avg_pairwise_corr
from jarvis.portfolio.returns_matrix import (
    EventReturnSource,
    MTMReturnSource,
    Position,
    ReturnMatrix,
    business_days,
    buyback_source,
)


def _cal(a, b):
    return business_days(a, b)


# ── 자료형/스키마 ────────────────────────────────────────────
def test_series_rows_match_requested_schema():
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-08", 0.1)])
    series = ReturnMatrix([src]).build()["S"]
    row = series.rows()[0]
    assert set(row) == {"strategy_id", "date", "return", "equity_curve", "exposure"}


# ── no-lookahead ─────────────────────────────────────────────
def test_no_lookahead_realized_only_on_exit():
    # 청산일(2026-01-08) 이전 날짜엔 수익 0, 청산일에만 계상
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-08", 0.1)])
    series = ReturnMatrix([src]).build(calendar=_cal("2026-01-05", "2026-01-09"))["S"]
    by = dict(zip(series.dates, series.returns))
    assert by["2026-01-05"] == 0.0 and by["2026-01-06"] == 0.0 and by["2026-01-07"] == 0.0
    assert by["2026-01-08"] == 0.1                        # 청산일에만
    # 보유창 동안 exposure=1, 청산일 이후 0
    ex = dict(zip(series.dates, series.exposure))
    assert ex["2026-01-05"] == 1.0 and ex["2026-01-07"] == 1.0 and ex["2026-01-08"] == 0.0


def test_no_lookahead_truncated_calendar_matches():
    # 캘린더를 청산 전에서 끊어도 이전 날짜 값은 동일(미래 실현 안 샘)
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-12", 0.2)])
    short = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-09"))["S"]
    long = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-15"))["S"]
    short_map = dict(zip(short.dates, short.returns))
    long_map = dict(zip(long.dates, long.returns))
    for d in short.dates:
        assert short_map[d] == long_map[d]               # 공유 구간 동일
    assert all(r == 0.0 for r in short.returns)          # 청산 전이라 전부 0


def test_open_position_no_return_but_exposure():
    # 미청산(realized None) → 수익 없음, exposure만
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-20", None)])
    series = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-10"))["S"]
    assert all(r == 0.0 for r in series.returns)
    assert series.active is True                          # exposure 있으니 active
    assert series.exposure[0] == 1.0


# ── 결정성 ───────────────────────────────────────────────────
def test_deterministic():
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-08", 0.1),
                                  Position("B", "2026-01-06", "2026-01-09", -0.05)])
    a = ReturnMatrix([src]).build()
    b = ReturnMatrix([src]).build()
    assert a["S"].rows() == b["S"].rows()


# ── 정렬/결측일 ──────────────────────────────────────────────
def test_alignment_common_calendar_and_missing_dates():
    s1 = EventReturnSource("S1", [Position("A", "2026-01-05", "2026-01-08", 0.1)])
    s2 = EventReturnSource("S2", [Position("B", "2026-01-12", "2026-01-15", 0.2)])
    m = ReturnMatrix([s1, s2])
    built = m.build()
    cal = m.calendar()
    # 공통 캘린더 = 두 전략 활동범위 합집합의 영업일
    assert built["S1"].dates == cal and built["S2"].dates == cal
    # S1은 S2 활동일에 수익 0(결측=flat)
    s1map = dict(zip(built["S1"].dates, built["S1"].returns))
    assert s1map["2026-01-13"] == 0.0


def test_equity_curve_compounds():
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-06", 0.1),
                                  Position("C", "2026-01-06", "2026-01-07", 0.1)])
    series = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-08"))["S"]
    # 0.1, 0.1 두 번 복리 → 최종 ~1.21
    assert abs(series.equity_curve[-1] - 1.21) < 1e-6


# ── 겹침 포지션 ──────────────────────────────────────────────
def test_overlapping_positions_exposure_and_mean_return():
    # 같은 날 두 포지션 보유 → capacity=2면 exposure=1.0; 같은날 청산 두 건 → 평균
    src = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-08", 0.10),
                                  Position("B", "2026-01-05", "2026-01-08", 0.20)])
    series = ReturnMatrix([src], capacity=2.0).build(_cal("2026-01-05", "2026-01-09"))["S"]
    ex = dict(zip(series.dates, series.exposure))
    ret = dict(zip(series.dates, series.returns))
    assert ex["2026-01-05"] == 1.0                        # 2/2
    assert ret["2026-01-08"] == 0.15                      # (0.1+0.2)/2 평균


# ── 비활동 전략 ──────────────────────────────────────────────
def test_inactive_strategy():
    src = EventReturnSource("EMPTY", [])
    other = EventReturnSource("S", [Position("A", "2026-01-05", "2026-01-08", 0.1)])
    built = ReturnMatrix([other, src]).build()
    assert built["EMPTY"].active is False
    assert all(r == 0.0 for r in built["EMPTY"].returns)


# ── MTM(선물/일별) 소스 ──────────────────────────────────────
def test_mtm_source_daily_returns_with_prices():
    prices = {("ES", "2026-01-05"): 100, ("ES", "2026-01-06"): 110, ("ES", "2026-01-07"): 99}
    src = MTMReturnSource("futures_tsmom", [Position("ES", "2026-01-05", "2026-01-08", None, 1)],
                          price_provider=lambda inst, d: prices.get((inst, d)))
    series = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-08"))["futures_tsmom"]
    by = dict(zip(series.dates, series.returns))
    assert abs(by["2026-01-06"] - 0.10) < 1e-9            # 100→110
    assert abs(by["2026-01-07"] - (99 / 110 - 1)) < 1e-9  # 110→99


def test_mtm_no_price_provider_inactive():
    src = MTMReturnSource("futures_tsmom", [Position("ES", "2026-01-05", "2026-01-08", None, 1)])
    series = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-08"))["futures_tsmom"]
    assert all(r == 0.0 for r in series.returns)          # 데이터 없음 = inactive 수익
    assert series.active is True                           # 단 exposure는 있음


def test_mtm_no_lookahead_uses_only_prev_and_current():
    # 미래 가격을 넣어도 특정일 수익은 prev/cur만 사용
    prices = {("X", "2026-01-05"): 100, ("X", "2026-01-06"): 110,
              ("X", "2026-01-07"): 9999}  # 미래 극단값
    src = MTMReturnSource("f", [Position("X", "2026-01-05", "2026-01-08", None, 1)],
                          price_provider=lambda i, d: prices.get((i, d)))
    series = ReturnMatrix([src]).build(_cal("2026-01-05", "2026-01-07"))["f"]
    by = dict(zip(series.dates, series.returns))
    assert abs(by["2026-01-06"] - 0.10) < 1e-9            # 06 수익은 07 극단값과 무관


# ── 상관계산 일관성 ──────────────────────────────────────────
def test_correlation_consistency_with_backtest():
    p = {("U", d): v for d, v in [("2026-01-05", 100), ("2026-01-06", 101),
                                  ("2026-01-07", 103), ("2026-01-08", 102), ("2026-01-09", 104)]}
    q = {("D", d): v for d, v in [("2026-01-05", 100), ("2026-01-06", 99),
                                  ("2026-01-07", 98), ("2026-01-08", 100), ("2026-01-09", 97)]}
    prov = lambda i, d: p.get((i, d)) or q.get((i, d))
    s1 = MTMReturnSource("U", [Position("U", "2026-01-05", "2026-01-10", None, 1)], prov)
    s2 = MTMReturnSource("D", [Position("D", "2026-01-05", "2026-01-10", None, 1)], prov)
    m = ReturnMatrix([s1, s2])
    cal, aligned = m.aligned()
    # ReturnMatrix.correlation == backtest.avg_pairwise_corr(정렬된 수익) → 일관
    assert m.correlation() == avg_pairwise_corr(aligned)


# ── 실 buyback 원장 스모크 ───────────────────────────────────
def test_buyback_source_builds_from_injected_rows():
    rows = [{"stock_code": "A", "entry_date": "2026-06-01", "exit_date": "2026-06-29",
             "pnl_pct": 0.05, "hold_days": 20},
            {"stock_code": "B", "entry_date": "2026-06-02", "hold_days": 20}]  # open, no pnl
    src = buyback_source(rows)
    series = ReturnMatrix([src]).build()
    s = series["kr_dart_buyback_drift_v1"]
    assert s.active is True
    # A 청산일에 0.05 계상, B는 실현 없음(open)
    assert any(abs(r - 0.05) < 1e-9 for r in s.returns)
