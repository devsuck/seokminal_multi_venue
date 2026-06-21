# tests/test_client.py
from unittest.mock import MagicMock

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
