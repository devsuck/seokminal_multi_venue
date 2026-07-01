"""KRX OpenAPI client.

Auth: AUTH_KEY as query parameter, body as JSON POST
Base URL: https://data-dbg.krx.co.kr (set via KRX_BASE_URL env var)

Confirmed working paths:
  idx/krx_dd_trd       — KRX 전체 지수 일별시세
  idx/kospi_dd_trd     — KOSPI 시리즈 지수 일별시세
  idx/kosdaq_dd_trd    — KOSDAQ 시리즈 지수 일별시세
  sto/stk_isu_base_info — 유가증권 종목 기본정보
  sto/ksq_isu_base_info — 코스닥 종목 기본정보
"""
from __future__ import annotations

import os
import requests
from datetime import date, timedelta

_DEFAULT_BASE = "https://data-dbg.krx.co.kr"


class KRXClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ["KRX_API_KEY"]
        self._base = base_url or os.environ.get("KRX_BASE_URL") or _DEFAULT_BASE
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "nautilus-quant/1.0"})

    def _post(self, path: str, body: dict) -> list[dict]:
        url = f"{self._base}/svc/apis/{path}"
        resp = self._session.post(
            url,
            params={"AUTH_KEY": self._api_key},
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("respCode") not in (None, "200", 200):
            raise RuntimeError(f"KRX error: {data}")
        if isinstance(data, list):
            return data
        for key in ("OutBlock_1", "output", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return []

    def get_index_daily(self, bas_dd: str, index_type: str = "KRX") -> list[dict]:
        """일별 지수 시세. index_type: 'KRX' | 'KOSPI' | 'KOSDAQ'"""
        path_map = {
            "KRX":    "idx/krx_dd_trd",
            "KOSPI":  "idx/kospi_dd_trd",
            "KOSDAQ": "idx/kosdaq_dd_trd",
        }
        path = path_map.get(index_type.upper(), "idx/krx_dd_trd")
        return self._post(path, {"basDd": bas_dd})

    def get_stock_base_info(self, market: str = "KOSPI") -> list[dict]:
        """종목 기본정보 (시가총액, 상장주수 등). market: 'KOSPI' | 'KOSDAQ'"""
        path = "sto/stk_isu_base_info" if market.upper() == "KOSPI" else "sto/ksq_isu_base_info"
        today = date.today().strftime("%Y%m%d")
        return self._post(path, {"basDd": today})

    def get_derivatives_daily(self, bas_dd: str, kind: str = "futures") -> list[dict]:
        """선물/옵션 일별 매매정보. kind: 'futures' | 'options'"""
        path = "drv/non_stk_fut_dd_trd" if kind == "futures" else "drv/non_stk_opt_dd_trd"
        return self._post(path, {"basDd": bas_dd})

    def get_etf_daily(self, bas_dd: str) -> list[dict]:
        """ETF 일별 매매정보."""
        return self._post("etf/etf_pd_dd_trd", {"basDd": bas_dd})

    def get_date_range(self, start: str, end: str, fetch_fn) -> list[dict]:
        """start~end 범위 일별 데이터 수집 (영업일 순회)."""
        results = []
        cur = date.fromisoformat(start[:4] + "-" + start[4:6] + "-" + start[6:8])
        end_dt = date.fromisoformat(end[:4] + "-" + end[4:6] + "-" + end[6:8])
        while cur <= end_dt:
            if cur.weekday() < 5:
                try:
                    rows = fetch_fn(cur.strftime("%Y%m%d"))
                    results.extend(rows)
                except Exception:
                    pass
            cur += timedelta(days=1)
        return results
