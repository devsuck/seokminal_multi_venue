"""DART client tests — elestock.json date-range post-filter + report-detail 지연일수 파싱."""
import io
import zipfile
from unittest.mock import MagicMock, patch

from insider.dart_client import get_executive_stock_changes, get_report_lag_days

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
