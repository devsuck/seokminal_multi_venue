from unittest.mock import MagicMock

import pytest
import requests

from backends.kis.order_client import KISOrderClient


def _mock_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _mock_401_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 401
    response.json.return_value = {"rt_cd": "1", "msg1": "token expired"}
    error = requests.HTTPError("401 Client Error")
    error.response = response
    response.raise_for_status.side_effect = error
    return response


def _client(session, auth=None):
    auth = auth or MagicMock()
    auth.get_access_token.return_value = "tok"
    return KISOrderClient(
        app_key="key",
        app_secret="secret",
        cano="12345678",
        acnt_prdt_cd="01",
        auth=auth,
        session=session,
    ), auth


def test_place_order_buy_limit_sends_expected_request_and_returns_payload():
    session = MagicMock()
    session.post.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000001234"}}
    )
    client, _ = _client(session)

    result = client.place_order(
        code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000
    )

    assert result["output"]["ODNO"] == "0000001234"
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args[0].endswith("/uapi/domestic-stock/v1/trading/order-cash")
    assert call.kwargs["headers"]["tr_id"] == "VTTC0802U"
    assert call.kwargs["json"]["CANO"] == "12345678"
    assert call.kwargs["json"]["ACNT_PRDT_CD"] == "01"
    assert call.kwargs["json"]["PDNO"] == "005930"
    assert call.kwargs["json"]["ORD_DVSN"] == "00"
    assert call.kwargs["json"]["ORD_QTY"] == "1"
    assert call.kwargs["json"]["ORD_UNPR"] == "65000"


def test_place_order_sell_market_uses_sell_tr_id_and_zero_price():
    session = MagicMock()
    session.post.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000005678"}}
    )
    client, _ = _client(session)

    client.place_order(code="005930", side="SELL", quantity=1, order_division="MARKET")

    call = session.post.call_args
    assert call.kwargs["headers"]["tr_id"] == "VTTC0801U"
    assert call.kwargs["json"]["ORD_DVSN"] == "01"
    assert call.kwargs["json"]["ORD_UNPR"] == "0"


def test_place_order_raises_runtime_error_on_nonzero_rt_cd():
    session = MagicMock()
    session.post.return_value = _mock_response({"rt_cd": "1", "msg1": "insufficient cash"})
    client, _ = _client(session)

    with pytest.raises(RuntimeError, match="insufficient cash"):
        client.place_order(code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000)


def test_place_order_raises_key_error_when_odno_missing():
    session = MagicMock()
    session.post.return_value = _mock_response({"rt_cd": "0", "msg1": "success", "output": {}})
    client, _ = _client(session)

    with pytest.raises(KeyError):
        client.place_order(code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000)


def test_place_order_retries_once_after_401_then_succeeds():
    session = MagicMock()
    session.post.side_effect = [
        _mock_401_response(),
        _mock_response({"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000001234"}}),
    ]
    auth = MagicMock()
    auth.get_access_token.side_effect = ["stale-tok", "fresh-tok"]
    client, auth = _client(session, auth=auth)

    result = client.place_order(code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000)

    assert result["output"]["ODNO"] == "0000001234"
    assert session.post.call_count == 2
    auth.invalidate.assert_called_once()


def test_get_order_status_returns_matching_row():
    session = MagicMock()
    session.get.return_value = _mock_response(
        {
            "rt_cd": "0",
            "msg1": "success",
            "output1": [
                {"ODNO": "0000001234", "ORD_DVSN": "00"},
                {"ODNO": "0000009999", "ORD_DVSN": "00"},
            ],
        }
    )
    client, _ = _client(session)

    result = client.get_order_status(order_date="20240603", order_no="0000001234")

    assert result == {"ODNO": "0000001234", "ORD_DVSN": "00"}
    call = session.get.call_args
    assert call.args[0].endswith("/uapi/domestic-stock/v1/trading/inquire-daily-ccld")
    assert call.kwargs["headers"]["tr_id"] == "VTTC8001R"
    assert call.kwargs["params"]["CANO"] == "12345678"
    assert call.kwargs["params"]["INQR_STRT_DT"] == "20240603"
    assert call.kwargs["params"]["INQR_END_DT"] == "20240603"


def test_get_order_status_returns_none_when_not_found():
    session = MagicMock()
    session.get.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output1": [{"ODNO": "0000009999"}]}
    )
    client, _ = _client(session)

    result = client.get_order_status(order_date="20240603", order_no="0000001234")

    assert result is None


def test_cancel_order_sends_expected_request_and_returns_payload():
    session = MagicMock()
    session.post.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000001234"}}
    )
    client, _ = _client(session)

    result = client.cancel_order(order_date="20240603", order_no="0000001234", code="005930", quantity=1)

    assert result["output"]["ODNO"] == "0000001234"
    call = session.post.call_args
    assert call.args[0].endswith("/uapi/domestic-stock/v1/trading/order-rvsecncl")
    assert call.kwargs["headers"]["tr_id"] == "VTTC0803U"
    assert call.kwargs["json"]["ORGN_ODNO"] == "0000001234"
    assert call.kwargs["json"]["RVSE_CNCL_DVSN_CD"] == "02"
    assert call.kwargs["json"]["ORD_QTY"] == "1"
