from __future__ import annotations

from research.paper.buyback_v3_dilution_forward import _has_dilution_overhang


def test_no_cb_history():
    assert _has_dilution_overhang([], "2026-06-01") is False


def test_cb_within_lookback():
    assert _has_dilution_overhang(["2026-04-01"], "2026-06-01") is True  # 61일 전


def test_cb_before_lookback():
    assert _has_dilution_overhang(["2026-01-01"], "2026-06-01") is False  # 151일 전


def test_cb_after_event_ignored():
    assert _has_dilution_overhang(["2026-07-01"], "2026-06-01") is False  # 미래 CB는 무관
