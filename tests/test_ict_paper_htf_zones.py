from research.ict.paper.htf_zones import ZoneTracker, ifvg_zones


def test_ifvg_zones_detects_bullish_zone_after_bearish_fvg_violation():
    h = [10, 9, 5, 12]
    l = [8, 7, 4, 11]
    c = [8.5, 7.5, 4.5, 11.5]
    zones = ifvg_zones(h, l, c, window=8)
    assert {"idx": 3, "type": "bullish", "zone_lo": 5, "zone_hi": 8} in zones


def test_ifvg_zones_returns_empty_when_no_violation():
    h = [10, 9, 5]
    l = [8, 7, 4]
    c = [8.5, 7.5, 4.5]
    assert ifvg_zones(h, l, c, window=8) == []


def test_zone_tracker_creates_ob_zone_and_finds_it_by_price():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    zone = tracker.zone_at_price(100.0)
    assert zone is not None
    assert zone["source"] == "OB"
    assert zone["type"] == "bullish"
    assert zone["zone_lo"] == 99
    assert zone["zone_hi"] == 101.5


def test_zone_tracker_zone_at_price_returns_none_outside_zone():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    assert tracker.zone_at_price(50.0) is None


def test_zone_tracker_invalidates_zone_on_opposite_close():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    # low=89 (not 99): keeps bar3's close (90) from dropping below this bar's low, so bar3
    # doesn't also qualify as a fresh (overlapping) bearish order block per order_blocks() —
    # this test only exercises invalidation of the existing bullish zone, not zone creation.
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 89, "close": 105})
    assert tracker.zone_at_price(100.0) is not None
    tracker.update({"ts": 1800, "open": 105, "high": 105, "low": 90, "close": 90})
    assert tracker.zone_at_price(100.0) is None


def test_zone_tracker_mark_consumed_removes_zone_from_active_lookup():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    zone = tracker.zone_at_price(100.0)
    tracker.mark_consumed(zone)
    assert tracker.zone_at_price(100.0) is None


def test_next_opposing_level_finds_nearest_swing_high_above_entry():
    tracker = ZoneTracker()
    bars = [
        {"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5},
        {"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105},
        {"ts": 1800, "open": 105, "high": 110, "low": 104, "close": 108},
        {"ts": 2700, "open": 103.5, "high": 104, "low": 100, "close": 103},
        {"ts": 3600, "open": 103, "high": 103, "low": 99.5, "close": 102},
    ]
    for bar in bars:
        tracker.update(bar)
    assert tracker.next_opposing_level("bullish", entry_price=101.0) == 110.0


def test_next_opposing_level_returns_none_when_no_swing_yet():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    assert tracker.next_opposing_level("bullish", entry_price=101.0) is None


def test_update_refeeding_same_overlapping_bars_is_a_noop():
    """REST 재폴링은 매번 최근 100개 봉을 다시 반환한다 — 이미 반영한 봉이 겹쳐 다시
    들어와도 존 개수/봉 히스토리 길이가 늘어나서는 안 된다(리뷰 C1 재현 케이스)."""
    bars = [
        {"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5},
        {"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105},
        {"ts": 1800, "open": 105, "high": 110, "low": 104, "close": 108},
        {"ts": 2700, "open": 103.5, "high": 104, "low": 100, "close": 103},
        {"ts": 3600, "open": 103, "high": 103, "low": 99.5, "close": 102},
    ]
    tracker = ZoneTracker()
    for bar in bars:
        tracker.update(bar)
    zone_count_after_first_pass = len(tracker._zones)
    bar_history_len_after_first_pass = len(tracker._c)

    # 재폴링 시뮬레이션: 동일한(겹치는) 100개 캔들 윈도우가 다음 사이클에 그대로 다시 들어옴
    for bar in bars:
        tracker.update(bar)

    assert len(tracker._zones) == zone_count_after_first_pass
    assert len(tracker._c) == bar_history_len_after_first_pass
    assert tracker.next_opposing_level("bullish", entry_price=101.0) == 110.0


def test_update_overwrites_forming_candle_in_place_instead_of_duplicating():
    """마지막 봉(진행 중인 봉)이 동일 ts로 다시 들어오면 새 봉으로 추가되지 않고 그 자리에서
    갱신되어야 한다 — 마감되지 않은 봉의 OHLC가 폴링마다 바뀌어도 봉 개수는 늘지 않는다."""
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 100, "low": 100, "close": 100})
    tracker.update({"ts": 900, "open": 100, "high": 100, "low": 100, "close": 100})  # 진행 중인 봉
    assert len(tracker._c) == 2

    # 같은 진행 중인 봉이 더 넓어진 고가/저가로 재폴링됨(아직 ts는 그대로)
    tracker.update({"ts": 900, "open": 100, "high": 105, "low": 95, "close": 102})
    assert len(tracker._c) == 2  # 새 봉으로 추가되지 않고 제자리 갱신
    assert tracker._h[-1] == 105
    assert tracker._l[-1] == 95
    assert tracker._c[-1] == 102


def test_update_ignores_stale_bar_older_than_last_seen_timestamp():
    tracker = ZoneTracker()
    tracker.update({"ts": 900, "open": 100, "high": 101, "low": 99, "close": 100.5})
    tracker.update({"ts": 1800, "open": 100.5, "high": 102, "low": 100, "close": 101})
    assert len(tracker._c) == 2

    # 재폴링 윈도우가 겹쳐서 훨씬 과거의 봉이 다시 들어옴 — 완전 무시(no-op)
    tracker.update({"ts": 0, "open": 999, "high": 999, "low": 999, "close": 999})
    assert len(tracker._c) == 2
    assert tracker._c[0] == 100.5  # 과거 봉이 시계열을 역행/오염시키지 않음


def test_zone_tracker_prunes_stale_invalidated_zones_and_does_not_grow_unbounded():
    """무효화/소진된 존은 OHLC 보유 윈도우(max_bars) 밖으로 밀려나면 정리되어야 한다 —
    24/7 상시 프로세스에서 _zones 딕셔너리가 무한정 커지는 것을 방지(리뷰 I1)."""
    tracker = ZoneTracker(max_bars=5)
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    assert tracker.zone_at_price(100.0) is not None
    bullish_key = ("OB", "bullish", 99, 101.5)
    assert bullish_key in tracker._zones

    tracker.update({"ts": 1800, "open": 105, "high": 105, "low": 90, "close": 90})
    assert bullish_key in tracker._zones  # 무효화 직후엔 아직 프루닝 윈도우 안 — 남아있음
    assert tracker._zones[bullish_key]["status"] == "invalidated"

    # max_bars(5)를 넘어설 만큼 도지(open==close) 봉을 더 흘려보낸다 — 신규 존을 만들지 않는
    # 중립 봉이므로 이 구간에서 존 증가는 오직 프루닝 유무만 반영한다.
    ts = 2700
    for _ in range(8):
        tracker.update({"ts": ts, "open": 90, "high": 91, "low": 89, "close": 90})
        ts += 900

    assert bullish_key not in tracker._zones  # 오래된 무효 존은 프루닝됨
    assert len(tracker._zones) == 1  # 남은 건 여전히 active한 존뿐 — 무한정 증가하지 않음
