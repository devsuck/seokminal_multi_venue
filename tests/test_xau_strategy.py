"""XAU 전략 상태머신 유닛테스트 — 합성 15m 바로 수학/상태 검증."""
from datetime import datetime

from research.xau_session.sessions import NY_TZ
from research.xau_session.strategy import Config, run


def _ts(mo, d, h, mi):
    return datetime(2026, mo, d, h, mi, tzinfo=NY_TZ).timestamp()


def _bars(rows):
    """rows: (ts, o, h, l, c) → dict of lists."""
    return {
        "ts": [r[0] for r in rows],
        "o": [r[1] for r in rows],
        "h": [r[2] for r in rows],
        "l": [r[3] for r in rows],
        "c": [r[4] for r in rows],
    }


# 아시안 hi=2030 lo=2000 (width 1.5% ≥ 1.2 필터 통과) 만드는 공통 프리앰블.
def _asian_range_2030_2000():
    return [
        (_ts(1, 15, 19, 0), 2015, 2030, 2000, 2015),   # asian start → hi/lo 세팅
        (_ts(1, 15, 21, 0), 2015, 2025, 2005, 2020),   # asian 내
        (_ts(1, 16, 2, 45), 2020, 2028, 2010, 2020),   # asian 마지막
        (_ts(1, 16, 3, 0), 2020, 2022, 2018, 2020),    # 03:00 종료봉 → 레인지 고정, 돌파 없음
    ]


def test_asian_range_fixed_then_london_long_tp():
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # 롱 돌파 진입 @2035
        (_ts(1, 16, 3, 30), 2035, 2053, 2034, 2050),   # h=2053 ≥ TP 2052.5 → tp
    ]
    trades = run(_bars(rows))
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == 1
    assert t.entry_price == 2035
    assert t.sl == 2000 and t.risk_per_unit == 35
    assert t.tp == 2052.5 and t.exit_reason == "tp" and t.exit_price == 2052.5


def test_london_long_sl():
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # 진입 @2035, sl=2000
        (_ts(1, 16, 3, 30), 2034, 2036, 1999, 2001),   # l=1999 ≤ sl 2000 → sl
    ]
    trades = run(_bars(rows))
    assert len(trades) == 1 and trades[0].exit_reason == "sl"
    assert trades[0].exit_price == 2000


def test_short_breakout_tp():
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 1999, 2000, 1990, 1995),   # 숏 돌파 @1995, sl=2030, risk=35, tp=1977.5
        (_ts(1, 16, 3, 30), 1994, 1996, 1976, 1980),   # l=1976 ≤ 1977.5 → tp
    ]
    trades = run(_bars(rows))
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == -1 and t.entry_price == 1995
    assert t.sl == 2030 and t.tp == 1977.5 and t.exit_reason == "tp"


def test_asian_width_filter_blocks_narrow_range():
    # hi=2010 lo=2000 → width 0.5% < 1.2 → 진입 차단.
    rows = [
        (_ts(1, 15, 19, 0), 2005, 2010, 2000, 2005),
        (_ts(1, 16, 3, 0), 2005, 2008, 2002, 2005),
        (_ts(1, 16, 3, 15), 2009, 2014, 2008, 2012),   # 돌파지만 width 미달
    ]
    assert run(_bars(rows)) == []


def test_london_breakout_dedup_one_per_cycle():
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # 진입
        (_ts(1, 16, 3, 30), 2035, 2053, 2034, 2050),   # TP 청산
        (_ts(1, 16, 3, 45), 2050, 2060, 2049, 2055),   # 또 hi 위 close지만 london_done → 무시
    ]
    trades = run(_bars(rows))
    assert len(trades) == 1   # dedup: 사이클당 런던돌파 1회


def test_ny_continuation_when_london_entry_off():
    cfg = Config(use_london_breakout=False, use_ny_continuation=True)
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # 런던돌파 → dir/level만 세팅(진입X)
        (_ts(1, 16, 8, 0), 2036, 2041, 2033, 2040),    # NY 세션 재돌파 → 진입 @2040
        (_ts(1, 16, 8, 15), 2040, 2061, 2039, 2058),   # TP 2060 도달
    ]
    trades = run(_bars(rows), cfg)
    assert len(trades) == 1
    t = trades[0]
    assert t.entry_price == 2040 and t.sl == 2000 and t.direction == 1
    assert t.tp == 2060 and t.exit_reason == "tp"


def test_no_entry_when_both_toggles_off():
    cfg = Config(use_london_breakout=False, use_ny_continuation=False)
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),
        (_ts(1, 16, 8, 0), 2036, 2041, 2033, 2040),
    ]
    assert run(_bars(rows), cfg) == []


def test_cycle_reset_uses_new_range():
    # 사이클1: hi=2030 lo=2000 진입/청산. 사이클2(다음날 19:00): 새 레인지 hi=2100 lo=2060.
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # c1 진입
        (_ts(1, 16, 3, 30), 2035, 2053, 2034, 2050),   # c1 tp
        # 사이클2 아시안
        (_ts(1, 16, 19, 0), 2080, 2100, 2060, 2080),   # 새 asian start → 새 hi/lo
        (_ts(1, 17, 2, 45), 2080, 2095, 2065, 2080),
        (_ts(1, 17, 3, 0), 2080, 2085, 2075, 2080),    # 고정 hi=2100 lo=2060 (width 1.9%)
        (_ts(1, 17, 3, 15), 2101, 2106, 2100, 2105),   # 새 레인지 돌파 → 진입 @2105 (risk=45, tp=2127.5)
        (_ts(1, 17, 3, 30), 2105, 2130, 2104, 2125),   # h=2130 ≥ tp 2127.5 → tp
    ]
    trades = run(_bars(rows))
    assert len(trades) == 2
    c2 = trades[1]
    assert c2.entry_price == 2105 and c2.sl == 2060 and c2.risk_per_unit == 45


def test_time_exit_toggle():
    cfg = Config(use_time_exit=True, max_bars_in_trade=2)
    rows = _asian_range_2030_2000() + [
        (_ts(1, 16, 3, 15), 2031, 2036, 2030, 2035),   # 진입
        (_ts(1, 16, 3, 30), 2035, 2040, 2031, 2036),   # bars_held=1, TP/SL 미도달
        (_ts(1, 16, 3, 45), 2036, 2041, 2032, 2038),   # bars_held=2 → time 청산 @close 2038
    ]
    trades = run(_bars(rows), cfg)
    assert len(trades) == 1 and trades[0].exit_reason == "time"
    assert trades[0].exit_price == 2038


def test_trailing_toggle_raises():
    import pytest
    with pytest.raises(NotImplementedError):
        run(_bars(_asian_range_2030_2000()), Config(use_trailing=True))
