# tests/test_client.py
from unittest.mock import MagicMock

import pytest
import requests

from backends.kis.client import KISClient


def _row(date: str, close: str = "70000") -> dict:
    return {
        "stck_bsop_date": date,
        "stck_oprc": "69500",
        "stck_hgpr": "70500",
        "stck_lwpr": "69000",
        "stck_clpr": close,
        "acml_vol": "1000000",
    }


def _mock_response(rows: list[dict]) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"output2": rows, "rt_cd": "0"}
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


def _mock_error_response(rt_cd: str = "1", msg1: str = "rate limit exceeded") -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"output2": [], "rt_cd": rt_cd, "msg1": msg1}
    response.raise_for_status.return_value = None
    return response


def test_get_daily_price_single_page_returns_rows_oldest_first():
    session = MagicMock()
    # KIS returns newest-first; client must reverse to oldest-first.
    rows_newest_first = [_row("20240103"), _row("20240102"), _row("20240101")]
    session.get.return_value = _mock_response(rows_newest_first)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20240101", "20240103")

    assert [r["stck_bsop_date"] for r in result] == ["20240101", "20240102", "20240103"]
    session.get.assert_called_once()
    call_kwargs = session.get.call_args.kwargs
    assert call_kwargs["headers"]["authorization"] == "Bearer tok"
    assert call_kwargs["headers"]["appkey"] == "key"
    assert call_kwargs["params"]["FID_INPUT_ISCD"] == "005930"


def test_get_daily_price_paginates_when_page_is_full(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    session = MagicMock()
    import datetime as dt

    page_end = dt.date(2024, 3, 31)
    full_page = [
        _row((page_end - dt.timedelta(days=i)).strftime("%Y%m%d")) for i in range(100)
    ]
    second_page = [_row("20231201")]
    session.get.side_effect = [
        _mock_response(full_page),
        _mock_response(second_page),
    ]
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20231201", "20240331")

    assert session.get.call_count == 2
    assert len(result) == 101


def test_get_daily_price_skips_blank_rows():
    session = MagicMock()
    rows = [_row("20240101"), {"stck_bsop_date": "", "stck_oprc": "", "stck_hgpr": "",
                                "stck_lwpr": "", "stck_clpr": "", "acml_vol": ""}]
    session.get.return_value = _mock_response(rows)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20240101", "20240101")

    assert len(result) == 1


def test_get_daily_price_retries_once_after_401_then_succeeds():
    session = MagicMock()
    rows = [_row("20240101")]
    session.get.side_effect = [_mock_401_response(), _mock_response(rows)]
    auth = MagicMock()
    auth.get_access_token.side_effect = ["stale-tok", "fresh-tok"]

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20240101", "20240101")

    assert [r["stck_bsop_date"] for r in result] == ["20240101"]
    assert session.get.call_count == 2
    auth.invalidate.assert_called_once()
    assert auth.get_access_token.call_count == 2
    # Second call must use the refreshed token.
    second_call_headers = session.get.call_args_list[1].kwargs["headers"]
    assert second_call_headers["authorization"] == "Bearer fresh-tok"


def test_get_daily_price_raises_when_401_persists_after_retry():
    session = MagicMock()
    session.get.side_effect = [_mock_401_response(), _mock_401_response()]
    auth = MagicMock()
    auth.get_access_token.side_effect = ["stale-tok", "still-stale-tok"]

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)

    with pytest.raises(requests.HTTPError):
        client.get_daily_price("005930", "20240101", "20240101")

    assert session.get.call_count == 2
    auth.invalidate.assert_called_once()


def test_get_daily_price_raises_runtime_error_on_nonzero_rt_cd():
    session = MagicMock()
    session.get.return_value = _mock_error_response(rt_cd="1", msg1="rate limit exceeded")
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)

    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        client.get_daily_price("005930", "20240101", "20240101")


def _index_row(date: str, close: str = "265032") -> dict:
    return {
        "stck_bsop_date": date,
        "bstp_nmix_oprc": "264500",
        "bstp_nmix_hgpr": "265500",
        "bstp_nmix_lwpr": "264000",
        "bstp_nmix_prpr": close,
        "acml_vol": "500000000",
    }


def test_get_daily_index_price_single_page_returns_rows_oldest_first():
    session = MagicMock()
    rows_newest_first = [_index_row("20240103"), _index_row("20240102"), _index_row("20240101")]
    session.get.return_value = _mock_response(rows_newest_first)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_index_price("0001", "20240101", "20240103")

    assert [r["stck_bsop_date"] for r in result] == ["20240101", "20240102", "20240103"]
    call_kwargs = session.get.call_args.kwargs
    assert call_kwargs["params"]["FID_COND_MRKT_DIV_CODE"] == "U"
    assert call_kwargs["params"]["FID_INPUT_ISCD"] == "0001"
    # KIS's index endpoint anchors pagination on FID_INPUT_DATE_1 (latest/end)
    # and uses FID_INPUT_DATE_2 as the lower bound (start) -- the opposite of
    # the stock endpoint's convention.
    assert call_kwargs["params"]["FID_INPUT_DATE_1"] == "20240103"
    assert call_kwargs["params"]["FID_INPUT_DATE_2"] == "20240101"


def test_get_daily_index_price_skips_blank_rows():
    session = MagicMock()
    rows = [
        _index_row("20240101"),
        {
            "stck_bsop_date": "",
            "bstp_nmix_oprc": "",
            "bstp_nmix_hgpr": "",
            "bstp_nmix_lwpr": "",
            "bstp_nmix_prpr": "",
            "acml_vol": "",
        },
    ]
    session.get.return_value = _mock_response(rows)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_index_price("0001", "20240101", "20240101")

    assert len(result) == 1
