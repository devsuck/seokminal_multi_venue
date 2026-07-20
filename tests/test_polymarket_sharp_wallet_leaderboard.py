from unittest.mock import Mock, patch

import research.polymarket_sharp_wallet.leaderboard as lb


def _entry(rank=1, wallet="0xABC", pnl=1000.0, vol=5000.0):
    return {"rank": rank, "proxyWallet": wallet, "pnl": pnl, "vol": vol}


def test_fetch_leaderboard_returns_parsed_list():
    fake_resp = Mock()
    fake_resp.json.return_value = [_entry(rank=1, wallet="0xAAA"), _entry(rank=2, wallet="0xBBB")]
    fake_resp.raise_for_status.return_value = None
    with patch.object(lb.requests, "get", return_value=fake_resp) as mock_get:
        result = lb.fetch_leaderboard()
    assert result == [
        {"rank": 1, "proxyWallet": "0xAAA", "pnl": 1000.0, "vol": 5000.0},
        {"rank": 2, "proxyWallet": "0xBBB", "pnl": 1000.0, "vol": 5000.0},
    ]
    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "category": lb.LEADERBOARD_CATEGORY, "timePeriod": lb.LEADERBOARD_TIME_PERIOD,
        "orderBy": "PNL", "limit": lb.LEADERBOARD_LIMIT, "offset": 0,
    }


def test_fetch_leaderboard_returns_empty_for_non_list_response():
    fake_resp = Mock()
    fake_resp.json.return_value = {"error": "bad"}
    fake_resp.raise_for_status.return_value = None
    with patch.object(lb.requests, "get", return_value=fake_resp):
        result = lb.fetch_leaderboard()
    assert result == []


def test_build_sharp_wallet_set_lowercases_keys():
    entries = [_entry(rank=1, wallet="0xABCDEF", pnl=500.0)]
    result = lb.build_sharp_wallet_set(entries)
    assert result == {"0xabcdef": {"rank": 1, "pnl": 500.0}}


def test_build_sharp_wallet_set_empty_input_returns_empty_dict():
    assert lb.build_sharp_wallet_set([]) == {}
