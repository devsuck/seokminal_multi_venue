"""DART client tests — elestock.json date-range post-filter + report-detail 지연일수 파싱."""
import io
import zipfile
from unittest.mock import MagicMock, patch

import insider.dart_client as dart_client
from insider.dart_client import (
    get_executive_stock_changes,
    get_recent_kr_corporate_actions,
    get_recent_kr_insider_feed,
    get_report_lag_days,
    search_company,
)

_RAW_LIST = [
    {"rcept_no": "1", "rcept_dt": "2024-08-07", "corp_code": "00126380", "corp_name": "삼성전자",
     "repror": "A", "isu_exctv_rgist_at": "", "isu_exctv_ofcps": "", "isu_main_shrholdr": "-",
     "sp_stock_lmp_cnt": "2,000", "sp_stock_lmp_irds_cnt": "1,000", "sp_stock_lmp_rate": "0", "sp_stock_lmp_irds_rate": "0"},
    {"rcept_no": "2", "rcept_dt": "2026-07-15", "corp_code": "00126380", "corp_name": "삼성전자",
     "repror": "B", "isu_exctv_rgist_at": "", "isu_exctv_ofcps": "", "isu_main_shrholdr": "-",
     "sp_stock_lmp_cnt": "500", "sp_stock_lmp_irds_cnt": "-500", "sp_stock_lmp_rate": "0", "sp_stock_lmp_irds_rate": "0"},
    {"rcept_no": "3", "rcept_dt": "2026-08-01", "corp_code": "00126380", "corp_name": "삼성전자",
     "repror": "C", "isu_exctv_rgist_at": "", "isu_exctv_ofcps": "", "isu_main_shrholdr": "-",
     "sp_stock_lmp_cnt": "300", "sp_stock_lmp_irds_cnt": "300", "sp_stock_lmp_rate": "0", "sp_stock_lmp_irds_rate": "0"},
]


def test_get_executive_stock_changes_filters_by_date_even_if_dart_ignores_params():
    """DART가 bgn_de/end_de 무시하고 전체이력 돌려줘도, 요청한 날짜범위 밖 rows는 걸러져야 함."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "000", "list": _RAW_LIST}
    with patch("insider.dart_client.requests.get", return_value=mock_resp), \
         patch("insider.dart_client._key", return_value="dummy"):
        rows = get_executive_stock_changes("00126380", "20260701", "20260802")

    assert len(rows) == 2  # 2024-08-07은 범위 밖이라 제외
    assert {r["rcept_dt"] for r in rows} == {"2026-07-15", "2026-08-01"}


def _fake_report_zip(mdf_dm_values: list[str]) -> bytes:
    rows = "".join(f'<TU AUNIT="MDF_DM" AUNITVALUE="{v}">x</TU>' for v in mdf_dm_values)
    xml = f'<?xml version="1.0"?><DOCUMENT>{rows}</DOCUMENT>'.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("rcept.xml", xml)
    return buf.getvalue()


def test_get_report_lag_days_computes_lag_from_real_transaction_date():
    """2026-07-30 변동 → 2026-08-02 접수 = 3일 지연. 실제 삼성전자 리포트(20240807000304)에서
    확인한 MDF_DM 포맷(AUNIT="MDF_DM" AUNITVALUE="YYYYMMDD")을 그대로 재현."""
    mock_resp = MagicMock()
    mock_resp.content = _fake_report_zip(["20260730", "20260728"])
    with patch("insider.dart_client.requests.get", return_value=mock_resp), \
         patch("insider.dart_client._key", return_value="dummy"):
        lags = get_report_lag_days("20260802000001", "2026-08-02")

    assert lags == [3, 5]


def test_get_report_lag_days_no_detail_table_returns_empty():
    mock_resp = MagicMock()
    mock_resp.content = _fake_report_zip([])
    with patch("insider.dart_client.requests.get", return_value=mock_resp), \
         patch("insider.dart_client._key", return_value="dummy"):
        lags = get_report_lag_days("20260802000001", "2026-08-02")

    assert lags == []


def _fake_corp_code_zip() -> bytes:
    xml = (
        '<?xml version="1.0"?><result>'
        '<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>'
        '<stock_code>005930</stock_code><modify_date>20260101</modify_date></list>'
        '<list><corp_code>00164742</corp_code><corp_name>삼성전자우</corp_name>'
        '<stock_code>005935</stock_code><modify_date>20260101</modify_date></list>'
        '<list><corp_code>00999999</corp_code><corp_name>비상장회사</corp_name>'
        '<stock_code></stock_code><modify_date>20260101</modify_date></list>'
        '</result>'
    ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


def test_search_company_filters_by_name_and_listed_only():
    """company.json은 corp_code 단건조회 전용이라 이름검색 불가 —
    corpCode.xml 전체목록을 받아 로컬에서 이름 부분일치 + 상장사(stock_code 有)만 필터."""
    dart_client._corp_list_cache = []
    dart_client._corp_list_cache_ts = 0.0
    mock_resp = MagicMock()
    mock_resp.content = _fake_corp_code_zip()
    with patch("insider.dart_client.requests.get", return_value=mock_resp) as mock_get, \
         patch("insider.dart_client._key", return_value="dummy"):
        results = search_company("삼성전자")

    assert mock_get.call_args.kwargs["params"] == {"crtfc_key": "dummy"}
    assert [r["corp_name"] for r in results] == ["삼성전자", "삼성전자우"]
    assert results[0]["corp_code"] == "00126380"
    assert results[0]["stock_code"] == "005930"


def test_search_company_uses_cache_on_second_call():
    dart_client._corp_list_cache = []
    dart_client._corp_list_cache_ts = 0.0
    mock_resp = MagicMock()
    mock_resp.content = _fake_corp_code_zip()
    with patch("insider.dart_client.requests.get", return_value=mock_resp) as mock_get, \
         patch("insider.dart_client._key", return_value="dummy"):
        search_company("삼성전자")
        search_company("삼성전자우")

    mock_get.assert_called_once()  # 두번째 호출은 캐시 히트, 재요청 없음


def test_search_company_empty_query_returns_empty_without_network():
    dart_client._corp_list_cache = []
    dart_client._corp_list_cache_ts = 0.0
    with patch("insider.dart_client.requests.get") as mock_get:
        assert search_company("   ") == []
    mock_get.assert_not_called()


def test_get_recent_kr_insider_feed_uses_explicit_window_when_given():
    """bgn_de/end_de 명시하면 today-days 대신 그 값을 그대로 씀 — 과거 백필용."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "000", "list": []}
    with patch("insider.dart_client.requests.get", return_value=mock_resp) as mock_get, \
         patch("insider.dart_client._key", return_value="dummy"):
        get_recent_kr_insider_feed(bgn_de="20260101", end_de="20260107")

    params = mock_get.call_args.kwargs["params"]
    assert params["bgn_de"] == "20260101"
    assert params["end_de"] == "20260107"


def test_get_recent_kr_corporate_actions_uses_explicit_window_when_given():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "000", "list": []}
    with patch("insider.dart_client.requests.get", return_value=mock_resp) as mock_get, \
         patch("insider.dart_client._key", return_value="dummy"):
        get_recent_kr_corporate_actions(bgn_de="20260101", end_de="20260107")

    params = mock_get.call_args.kwargs["params"]
    assert params["bgn_de"] == "20260101"
    assert params["end_de"] == "20260107"
