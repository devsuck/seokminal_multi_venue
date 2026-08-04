import datetime as dt
import json
from unittest.mock import patch

import research.run_options_uoa_collect as collect

ROW_A = {"ticker": "AAPL", "contract_symbol": "AAPL240101C00100000", "vol_oi_ratio": 5.0}
ROW_B = {"ticker": "MSFT", "contract_symbol": "MSFT240101C00100000", "vol_oi_ratio": 4.0}


def test_candidate_tickers_dedupes_form4_and_congress_in_order():
    with patch.object(collect, "get_recent_feed", return_value=[{"ticker": "AAPL"}, {"ticker": "MSFT"}]), \
         patch.object(collect, "get_congress_trades", return_value=[{"ticker": "MSFT"}, {"ticker": "GOOG"}]):
        tickers = collect.candidate_tickers(max_tickers=15)
    assert tickers == ["AAPL", "MSFT", "GOOG"]


def test_candidate_tickers_survives_source_failure():
    with patch.object(collect, "get_recent_feed", side_effect=ConnectionError("down")), \
         patch.object(collect, "get_congress_trades", return_value=[{"ticker": "GOOG"}]):
        tickers = collect.candidate_tickers()
    assert tickers == ["GOOG"]


def test_run_once_dedupes_against_already_logged_events_today(tmp_path):
    with patch.object(collect, "_DATA_DIR", tmp_path):
        collect.append_events([ROW_A | {"detected_at": "x"}])
        with patch.object(collect, "candidate_tickers", return_value=["AAPL", "MSFT"]), \
             patch.object(collect, "get_unusual_options_activity", return_value=[ROW_A, ROW_B]):
            new_rows = collect.run_once()
    assert [r["contract_symbol"] for r in new_rows] == [ROW_B["contract_symbol"]]
    assert "detected_at" in new_rows[0]


def test_append_events_appends_to_dated_file(tmp_path):
    with patch.object(collect, "_DATA_DIR", tmp_path):
        collect.append_events([ROW_A])
        collect.append_events([ROW_B])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["contract_symbol"] == ROW_B["contract_symbol"]


def test_append_events_skips_write_when_empty(tmp_path):
    with patch.object(collect, "_DATA_DIR", tmp_path):
        collect.append_events([])
    assert list(tmp_path.iterdir()) == []


def test_run_forever_stops_after_max_iterations_and_sleeps_between_not_after():
    with patch.object(collect, "run_once", return_value=[ROW_A]) as mock_run, \
         patch.object(collect, "append_events") as mock_append, \
         patch.object(collect.time, "sleep") as mock_sleep:
        collect.run_forever(poll_interval_sec=1, max_iterations=3)
    assert mock_run.call_count == 3
    assert mock_append.call_count == 3
    assert mock_sleep.call_count == 2


def test_run_forever_survives_run_once_exception_and_backs_off():
    with patch.object(collect, "run_once", side_effect=[ConnectionError("net down"), [ROW_A]]), \
         patch.object(collect, "append_events") as mock_append, \
         patch.object(collect.time, "sleep") as mock_sleep:
        collect.run_forever(poll_interval_sec=1, max_iterations=2)
    mock_append.assert_called_once_with([ROW_A])
    assert mock_sleep.call_count == 1
