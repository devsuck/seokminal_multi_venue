import datetime as dt
import json
from unittest.mock import patch

import research.run_convergence_signal_collect as collect

LEG_A = {"source": "dart_exec", "ticker": "005930", "direction": "BULLISH", "trade_date": "2026-08-01"}
LEG_B = {"source": "dart_corp_action", "ticker": "005930", "direction": "BULLISH", "trade_date": "2026-08-01"}


def test_collect_us_legs_prioritizes_overlapping_tickers_for_uoa():
    form4_us = {"source": "form4", "ticker": "TSLA", "direction": "BULLISH", "trade_date": "2026-08-01"}
    congress_us = {"source": "congress", "ticker": "TSLA", "direction": "BULLISH", "trade_date": "2026-08-01"}
    with patch.object(collect, "_tag_us_legs_without_uoa", return_value=[form4_us, congress_us]), \
         patch.object(collect, "_tag_uoa_legs", return_value=[]) as mock_uoa:
        collect._collect_us_legs(days=7)
    mock_uoa.assert_called_once_with(["TSLA"])


def test_run_once_tags_kr_and_us_legs_with_detected_at():
    with patch.object(collect, "_tag_kr_legs", return_value=[LEG_A]), \
         patch.object(collect, "_collect_us_legs", return_value=[]):
        legs = collect.run_once()
    assert len(legs) == 1
    assert "detected_at" in legs[0]


def test_run_once_survives_source_failure():
    with patch.object(collect, "_tag_kr_legs", side_effect=ConnectionError("down")), \
         patch.object(collect, "_collect_us_legs", return_value=[LEG_A]):
        legs = collect.run_once()
    assert len(legs) == 1


def test_run_once_dedupes_against_already_logged_legs_today(tmp_path):
    with patch.object(collect, "_DATA_DIR", tmp_path):
        collect.append_events([LEG_A | {"detected_at": "x"}])
        with patch.object(collect, "_tag_kr_legs", return_value=[LEG_A, LEG_B]), \
             patch.object(collect, "_collect_us_legs", return_value=[]):
            new_legs = collect.run_once()
    assert [collect.event_key(leg) for leg in new_legs] == [collect.event_key(LEG_B)]


def test_append_events_appends_to_dated_file(tmp_path):
    with patch.object(collect, "_DATA_DIR", tmp_path):
        collect.append_events([LEG_A])
        collect.append_events([LEG_B])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["source"] == "dart_corp_action"


def test_append_events_skips_write_when_empty(tmp_path):
    with patch.object(collect, "_DATA_DIR", tmp_path):
        collect.append_events([])
    assert list(tmp_path.iterdir()) == []


def test_run_forever_stops_after_max_iterations_and_sleeps_between_not_after():
    with patch.object(collect, "run_once", return_value=[LEG_A]) as mock_run, \
         patch.object(collect, "append_events") as mock_append, \
         patch.object(collect.time, "sleep") as mock_sleep:
        collect.run_forever(poll_interval_sec=1, max_iterations=3)
    assert mock_run.call_count == 3
    assert mock_append.call_count == 3
    assert mock_sleep.call_count == 2


def test_run_forever_survives_run_once_exception_and_backs_off():
    with patch.object(collect, "run_once", side_effect=[ConnectionError("net down"), [LEG_A]]), \
         patch.object(collect, "append_events") as mock_append, \
         patch.object(collect.time, "sleep") as mock_sleep:
        collect.run_forever(poll_interval_sec=1, max_iterations=2)
    mock_append.assert_called_once_with([LEG_A])
    assert mock_sleep.call_count == 1
