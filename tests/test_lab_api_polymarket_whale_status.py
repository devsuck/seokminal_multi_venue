from unittest.mock import patch

from api_server.lab_api import lab_status


def test_lab_status_processes_includes_polymarket_whale_tick():
    fake_status = {"running": False, "last_write": None, "age_sec": None}
    with patch("api_server.lab_api._tmux_process_status", return_value=fake_status) as mock_fn:
        result = lab_status()
    assert "polymarket_whale_tick" in result["processes"]
    calls = [c.args for c in mock_fn.call_args_list]
    assert ("polymarket-whale-tick", "research/data/polymarket_whale") in calls
