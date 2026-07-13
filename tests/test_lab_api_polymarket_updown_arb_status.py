from unittest.mock import patch

from api_server.lab_api import lab_status


def test_lab_status_processes_includes_polymarket_updown_arb():
    fake_status = {"running": False, "last_write": None, "age_sec": None}
    with patch("api_server.lab_api._tmux_process_status", return_value=fake_status) as mock_fn:
        result = lab_status()
    assert "polymarket_updown_arb" in result["processes"]
    calls = [c.args for c in mock_fn.call_args_list]
    assert ("polymarket-updown-arb", "research/data/polymarket_updown_arb") in calls
