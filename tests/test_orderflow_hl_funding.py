from orderflow.hl_funding import _cache, build_funding_snapshot, funding_poll_loop, get_cached_funding


def _universe(names):
    return [{"name": n, "szDecimals": 5, "maxLeverage": 50} for n in names]


def _ctx(funding, open_interest, mark_px, prev_day_px=0.0, day_ntl_vlm=0.0):
    return {
        "funding": funding,
        "openInterest": open_interest,
        "markPx": mark_px,
        "prevDayPx": prev_day_px,
        "dayNtlVlm": day_ntl_vlm,
    }


def test_build_funding_snapshot_maps_coin_to_parsed_floats():
    universe = _universe(["BTC", "ETH"])
    ctxs = [
        _ctx("0.0001", "5000.0", "95000.0", "93000.0", "5e8"),
        _ctx("-0.0002", "12000.0", "3200.0", "3100.0", "2e8"),
    ]
    snapshot = build_funding_snapshot(universe, ctxs, now=1000.0)

    assert set(snapshot) == {"BTC", "ETH"}
    assert snapshot["BTC"] == {
        "coin": "BTC",
        "funding": 0.0001,
        "open_interest": 5000.0,
        "mark_px": 95000.0,
        "prev_day_px": 93000.0,
        "day_ntl_vlm": 5e8,
        "updated_at": 1000.0,
    }
    assert snapshot["ETH"]["funding"] == -0.0002


def test_build_funding_snapshot_skips_entries_missing_name_or_fields():
    universe = [{"szDecimals": 5}, {"name": "SOL"}]
    ctxs = [_ctx("0.0001", "1.0", "100.0"), {"funding": "bad"}]
    snapshot = build_funding_snapshot(universe, ctxs, now=1000.0)
    assert snapshot == {}


def test_build_funding_snapshot_empty_inputs_returns_empty_dict():
    assert build_funding_snapshot([], [], now=1000.0) == {}


def test_get_cached_funding_uppercases_lookup():
    _cache.clear()
    _cache["BTC"] = {"coin": "BTC", "funding": 0.0001}
    try:
        assert get_cached_funding("btc") == {"coin": "BTC", "funding": 0.0001}
        assert get_cached_funding("DOGE") is None
    finally:
        _cache.clear()


async def test_funding_poll_loop_populates_cache_then_stops_on_sleep_cancel():
    _cache.clear()
    universe = _universe(["BTC"])
    ctxs = [_ctx("0.0001", "5000.0", "95000.0")]

    calls = {"n": 0}

    def fetch_fn():
        calls["n"] += 1
        return universe, ctxs

    import asyncio

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError

    import orderflow.hl_funding as hl_funding_mod
    orig_sleep = hl_funding_mod.asyncio.sleep
    hl_funding_mod.asyncio.sleep = fake_sleep
    try:
        try:
            await funding_poll_loop(fetch_fn=fetch_fn)
        except asyncio.CancelledError:
            pass
    finally:
        hl_funding_mod.asyncio.sleep = orig_sleep

    assert calls["n"] == 1
    assert get_cached_funding("BTC")["open_interest"] == 5000.0
    _cache.clear()


async def test_funding_poll_loop_preserves_last_cache_on_fetch_failure():
    _cache.clear()
    _cache["BTC"] = {"coin": "BTC", "funding": 0.0001, "open_interest": 5000.0,
                      "mark_px": 95000.0, "prev_day_px": 93000.0, "day_ntl_vlm": 5e8, "updated_at": 1.0}

    def failing_fetch_fn():
        raise RuntimeError("boom")

    import asyncio

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError

    import orderflow.hl_funding as hl_funding_mod
    orig_sleep = hl_funding_mod.asyncio.sleep
    hl_funding_mod.asyncio.sleep = fake_sleep
    try:
        try:
            await funding_poll_loop(fetch_fn=failing_fetch_fn)
        except asyncio.CancelledError:
            pass
    finally:
        hl_funding_mod.asyncio.sleep = orig_sleep

    assert get_cached_funding("BTC")["open_interest"] == 5000.0
    _cache.clear()
