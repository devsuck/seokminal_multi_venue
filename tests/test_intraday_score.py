"""Intraday (day-trading) scoring engine."""
from datetime import datetime, timedelta, timezone

from api_server import intraday_score as iz


def _bars(closes, vols=None, start_et_hour=10, base_range=0.5):
    """Build 5-min bars from a close series, timestamped from start_et_hour ET.

    Each bar's high/low straddle the close by ``base_range`` so ATR is non-trivial.
    ET 10:00 = 14:00 UTC (EDT) — avoids the midday-chop damp window.
    """
    vols = vols or [1000] * len(closes)
    bars = []
    t0 = datetime(2026, 6, 30, start_et_hour + 4, 0, tzinfo=timezone.utc)  # ET+4 → UTC
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        h = max(o, c) + base_range
        l = min(o, c) - base_range
        bars.append({"t": t0 + timedelta(minutes=5 * i), "o": o, "h": h, "l": l, "c": c, "v": vols[i]})
        prev = c
    return bars


def test_insufficient_data_avoids():
    out = iz.score_intraday(_bars([100, 101, 102]))
    assert out["signal"] == "AVOID"
    assert out["direction"] == "FLAT"


def test_dead_low_volatility_avoids():
    # Flat line → ATR ~0 → below tradeable floor → AVOID
    bars = _bars([100.0] * 12, base_range=0.0001)
    out = iz.score_intraday(bars)
    assert out["signal"] == "AVOID"
    assert "죽은" in out["reason"] or "변동성" in out.get("reason", "")


def test_long_breakout_is_long_and_actionable():
    # OR (first 6 bars) ~100±0.5, then breakout up with surging volume.
    closes = [100, 100.2, 99.8, 100.1, 100.3, 100.0,  # opening range
              101.5, 102.2, 103.0, 102.6, 103.4, 104.0]
    vols = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    out = iz.score_intraday(_bars(closes, vols))
    assert out["direction"] == "LONG"
    assert out["signal"] in ("BUY", "STRONG_BUY")
    # ATR-based risk levels: long stop below entry, target above, 1.5R
    assert out["stop"] < out["entry"] < out["target"]


def test_short_breakdown_is_short():
    closes = [100, 99.8, 100.2, 99.9, 100.1, 100.0,   # opening range
              98.5, 97.8, 97.0, 97.3, 96.5, 96.0]
    vols = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    out = iz.score_intraday(_bars(closes, vols))
    assert out["direction"] == "SHORT"
    assert out["stop"] > out["entry"] > out["target"]


def test_low_rvol_scores_lower_than_high_rvol():
    closes = [100, 100.2, 99.8, 100.1, 100.3, 100.0, 101.5, 102.2, 103.0, 102.6, 103.4, 104.0]
    hi_vol = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    lo_vol = [1000] * 11 + [300]  # last bar weak volume
    hi = iz.score_intraday(_bars(closes, hi_vol))
    lo = iz.score_intraday(_bars(closes, lo_vol))
    assert hi["score"] > lo["score"]


def test_midday_chop_dampens_score():
    closes = [100, 100.2, 99.8, 100.1, 100.3, 100.0, 101.5, 102.2, 103.0, 102.6, 103.4, 104.0]
    vols = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    morning = iz.score_intraday(_bars(closes, vols, start_et_hour=10))
    midday = iz.score_intraday(_bars(closes, vols, start_et_hour=12))  # 12:00 ET → chop window
    assert midday["score"] < morning["score"]


# ── component math ────────────────────────────────────────────────────────────

def test_vwap_matches_manual():
    bars = [
        {"t": datetime(2026, 6, 30, 14, 0, tzinfo=timezone.utc), "o": 10, "h": 11, "l": 9, "c": 10, "v": 100},
        {"t": datetime(2026, 6, 30, 14, 5, tzinfo=timezone.utc), "o": 10, "h": 13, "l": 11, "c": 12, "v": 300},
    ]
    # tp1=(11+9+10)/3=10 *100=1000 ; tp2=(13+11+12)/3=12 *300=3600 ; /400 = 11.5
    assert abs(iz.vwap(bars) - 11.5) < 1e-6


def test_opening_range_first_six_bars():
    closes = [100, 105, 95, 101, 99, 100, 200, 50]
    oh, ol = iz.opening_range(_bars(closes, base_range=0.0))
    # first 6 closes: max 105, min 95 (range 0 → high=close, low=close)
    assert oh == 105 and ol == 95


def test_relative_volume_last_vs_prior_avg():
    bars = _bars([100] * 5, vols=[100, 100, 100, 100, 400])
    # prior avg = 100, last = 400 → 4.0
    assert abs(iz.relative_volume(bars) - 4.0) < 1e-6


def test_crypto_mode_skips_session_and_tod():
    # Bars spanning multiple UTC days + midday-ET timestamps: crypto mode must
    # still use the whole window and not apply the midday damp.
    closes = [100, 100.2, 99.8, 100.1, 100.3, 100.0, 101.5, 102.2, 103.0, 102.6, 103.4, 104.0]
    vols = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    bars = _bars(closes, vols, start_et_hour=12)  # midday ET window
    crypto = iz.score_intraday(bars, crypto=True)
    equity = iz.score_intraday(bars)  # equity default: midday damp applies
    assert crypto["components"]["time_of_day"]["factor"] == 1.0
    assert equity["components"]["time_of_day"]["factor"] == 0.7
    assert crypto["score"] > equity["score"]  # no midday damp in crypto
    assert crypto["direction"] == "LONG"
    assert crypto["signal"] in ("BUY", "STRONG_BUY")


def test_kr_market_uses_kst_session():
    # Bars timestamped 10:00 KST (=01:00 UTC). KR session filter must keep them.
    from datetime import datetime, timedelta, timezone
    closes = [100, 100.2, 99.8, 100.1, 100.3, 100.0, 101.5, 102.2, 103.0, 102.6, 103.4, 104.0]
    vols = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    t0 = datetime(2026, 6, 30, 1, 0, tzinfo=timezone.utc)  # 10:00 KST
    bars, prev = [], closes[0]
    for i, c in enumerate(closes):
        bars.append({"t": t0 + timedelta(minutes=5 * i), "o": prev, "h": max(prev, c) + 0.5, "l": min(prev, c) - 0.5, "c": c, "v": vols[i]})
        prev = c
    out = iz.score_intraday(bars, market="KR")
    assert out["direction"] == "LONG"
    assert out["signal"] in ("BUY", "STRONG_BUY")
    assert out["components"]["time_of_day"]["factor"] == 1.0  # KR: no ToD damp
