import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_updown_arb_scan as scan


def test_append_snapshots_writes_jsonl_to_dated_file(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([{"condition_id": "a"}, {"condition_id": "b"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["condition_id"] == "a"
    assert json.loads(lines[1])["condition_id"] == "b"


def test_append_snapshots_skips_write_when_empty(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([])
    assert list(tmp_path.iterdir()) == []


def test_append_snapshots_appends_to_existing_file(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([{"condition_id": "a"}])
        scan.append_snapshots([{"condition_id": "b"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_run_once_selects_and_snapshots_updown_markets():
    fake_markets = [{"condition_id": "a"}]
    with patch.object(scan, "get_updown_markets", return_value=[{"condition_id": "raw"}]), \
         patch.object(scan, "select_updown_markets", return_value=fake_markets) as mock_sel, \
         patch.object(scan, "snapshot_market", return_value={"condition_id": "a"}) as mock_snap:
        snaps = scan.run_once()
    mock_sel.assert_called_once_with([{"condition_id": "raw"}])
    mock_snap.assert_called_once_with({"condition_id": "a"}, scan.FEE_BUFFER)
    assert snaps == [{"condition_id": "a"}]


def test_run_once_skips_markets_where_snapshot_fails():
    with patch.object(scan, "get_updown_markets", return_value=[]), \
         patch.object(scan, "select_updown_markets", return_value=[{"condition_id": "a"}, {"condition_id": "b"}]), \
         patch.object(scan, "snapshot_market", side_effect=[None, {"condition_id": "b"}]):
        snaps = scan.run_once()
    assert snaps == [{"condition_id": "b"}]


def test_run_forever_stops_after_max_iterations_and_sleeps_between_not_after():
    with patch.object(scan, "run_once", return_value=[{"condition_id": "a"}]) as mock_run, \
         patch.object(scan, "append_snapshots") as mock_append, \
         patch.object(scan.time, "sleep") as mock_sleep:
        scan.run_forever(poll_interval_sec=1, max_iterations=3)
    assert mock_run.call_count == 3
    assert mock_append.call_count == 3
    assert mock_sleep.call_count == 2
