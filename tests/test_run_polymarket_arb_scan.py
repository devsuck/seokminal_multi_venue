import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_arb_scan as scan


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


def test_run_forever_stops_after_max_iterations_and_sleeps_between_not_after():
    with patch.object(scan, "run_once", return_value=[{"condition_id": "a"}]) as mock_run, \
         patch.object(scan, "append_snapshots") as mock_append, \
         patch.object(scan.time, "sleep") as mock_sleep:
        scan.run_forever(poll_interval_sec=1, max_iterations=3)
    assert mock_run.call_count == 3
    assert mock_append.call_count == 3
    assert mock_sleep.call_count == 2


def test_run_forever_survives_run_once_exception_and_backs_off():
    """예외무가드였던 원래 루프는 여기서 프로세스가 죽었다(2026-08-02 polymarket_arb
    22분간 5회 재기동 실측) — try/except가 잡아 다음 이터레이션으로 넘어가야 한다."""
    with patch.object(scan, "run_once", side_effect=[ConnectionError("net down"), [{"condition_id": "a"}]]), \
         patch.object(scan, "append_snapshots") as mock_append, \
         patch.object(scan.time, "sleep") as mock_sleep:
        scan.run_forever(poll_interval_sec=1, max_iterations=2)
    mock_append.assert_called_once_with([{"condition_id": "a"}])
    assert mock_sleep.call_count == 1
