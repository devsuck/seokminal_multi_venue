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
