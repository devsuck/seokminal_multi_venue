from unittest.mock import Mock, patch

import research.polymarket_sharp_wallet.positions as pos


def test_fetch_wallet_positions_returns_list():
    fake_resp = Mock()
    fake_resp.json.return_value = [{"conditionId": "c1", "size": 10.0, "avgPrice": 0.5}]
    fake_resp.raise_for_status.return_value = None
    with patch.object(pos.requests, "get", return_value=fake_resp) as mock_get:
        result = pos.fetch_wallet_positions("0xabc")
    assert result == [{"conditionId": "c1", "size": 10.0, "avgPrice": 0.5}]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://data-api.polymarket.com/positions"
    assert kwargs["params"] == {"user": "0xabc"}


def test_fetch_wallet_positions_non_list_response_returns_empty():
    fake_resp = Mock()
    fake_resp.json.return_value = {"error": "bad"}
    fake_resp.raise_for_status.return_value = None
    with patch.object(pos.requests, "get", return_value=fake_resp):
        assert pos.fetch_wallet_positions("0xabc") == []


def test_fetch_wallet_positions_request_failure_returns_empty():
    with patch.object(pos.requests, "get", side_effect=Exception("boom")):
        assert pos.fetch_wallet_positions("0xabc") == []
