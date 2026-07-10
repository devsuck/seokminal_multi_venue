import datetime as dt
import math

import pytest

from options.pricer import bs_greeks
from orderflow.gex import _parse_deribit_expiry, fetch_gex_by_strike


def _fake_book_summary(instruments):
    async def fetch_fn(url, params):
        return {"result": instruments}
    return fetch_fn


def _instrument(name, underlying_price, mark_iv, open_interest):
    return {
        "instrument_name": name,
        "underlying_price": underlying_price,
        "mark_iv": mark_iv,
        "open_interest": open_interest,
    }


async def test_fetch_gex_by_strike_aggregates_call_and_put_at_same_strike():
    expiry_ts = _parse_deribit_expiry("27DEC26")
    now = expiry_ts - 30 * 86400.0  # 만기 30일 전
    instruments = [
        _instrument("BTC-27DEC26-100000-C", 95000.0, 55.0, 10.0),
        _instrument("BTC-27DEC26-100000-P", 95000.0, 55.0, 5.0),
    ]
    result = await fetch_gex_by_strike("BTC", fetch_fn=_fake_book_summary(instruments), now=now)

    assert result["currency"] == "BTC"
    assert result["spot"] == 95000.0
    assert result["updated_at"] == now
    assert len(result["levels"]) == 1
    level = result["levels"][0]
    assert level["strike"] == 100000.0

    T = 30 * 86400.0 / (365.0 * 86400.0)
    # BS 모델에서 gamma는 콜/풋 옵션타입에 무관하게 동일한 값이다.
    gamma = bs_greeks(95000.0, 100000.0, T, 0.0, 0.55, "call")["gamma"]
    expected_call_gex = gamma * 10.0 * (95000.0 ** 2) * 0.01
    expected_put_gex = gamma * 5.0 * (95000.0 ** 2) * 0.01

    assert math.isclose(level["call_gex"], expected_call_gex, rel_tol=1e-6)
    assert math.isclose(level["put_gex"], expected_put_gex, rel_tol=1e-6)
    assert math.isclose(level["net_gex"], expected_call_gex - expected_put_gex, rel_tol=1e-9)


async def test_fetch_gex_by_strike_skips_zero_oi_and_zero_iv():
    now = _parse_deribit_expiry("27DEC26") - 30 * 86400.0
    instruments = [
        _instrument("BTC-27DEC26-100000-C", 95000.0, 55.0, 0.0),   # OI=0 -> 스킵
        _instrument("BTC-27DEC26-110000-C", 95000.0, 0.0, 10.0),   # IV=0 -> 스킵
    ]
    result = await fetch_gex_by_strike("BTC", fetch_fn=_fake_book_summary(instruments), now=now)
    assert result["levels"] == []


async def test_fetch_gex_by_strike_ignores_malformed_instrument_name():
    now = _parse_deribit_expiry("27DEC26") - 30 * 86400.0
    instruments = [
        {"instrument_name": "BTC-PERPETUAL", "underlying_price": 95000.0, "mark_iv": 55.0, "open_interest": 10.0},
        _instrument("BTC-27DEC26-100000-C", 95000.0, 55.0, 10.0),
    ]
    result = await fetch_gex_by_strike("BTC", fetch_fn=_fake_book_summary(instruments), now=now)
    assert len(result["levels"]) == 1
    assert result["levels"][0]["strike"] == 100000.0


async def test_fetch_gex_by_strike_empty_instruments_returns_empty_levels():
    result = await fetch_gex_by_strike("ETH", fetch_fn=_fake_book_summary([]), now=1000.0)
    assert result == {"currency": "ETH", "spot": 0.0, "updated_at": 1000.0, "levels": []}


async def test_fetch_gex_by_strike_levels_sorted_by_strike():
    now = _parse_deribit_expiry("27DEC26") - 30 * 86400.0
    instruments = [
        _instrument("BTC-27DEC26-110000-C", 95000.0, 55.0, 10.0),
        _instrument("BTC-27DEC26-90000-C", 95000.0, 55.0, 10.0),
    ]
    result = await fetch_gex_by_strike("BTC", fetch_fn=_fake_book_summary(instruments), now=now)
    strikes = [lv["strike"] for lv in result["levels"]]
    assert strikes == sorted(strikes)


def test_parse_deribit_expiry_returns_utc_8am_epoch():
    ts = _parse_deribit_expiry("27DEC26")
    d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    assert (d.day, d.month, d.year, d.hour, d.minute) == (27, 12, 2026, 8, 0)
