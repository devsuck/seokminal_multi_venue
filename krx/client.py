"""KRX OpenAPI client.

Base URL: openapi.krx.co.kr (production after portal subscription approval)
Auth: apikey header

Confirmed working paths (data-dbg.krx.co.kr, 401 = path OK / key not activated):
  idx/krx_dd_trd       — KRX 전체 지수 일별시세
  idx/kospi_dd_trd     — KOSPI 시리즈 지수 일별시세
  idx/kosdaq_dd_trd    — KOSDAQ 시리즈 지수 일별시세
  sto/stk_isu_base_info — 유가증권 종목 기본정보
  sto/ksq_isu_base_info — 코스닥 종목 기본정보

Activation required at: https://openapi.krx.co.kr → 마이페이지 → 서비스 구독
After approval KRX sends production base URL (may differ per subscription).
"""
from __future__ import annotations

import os
import requests
from datetime import date, timedelta

# data-dbg = 테스트 서버 (경로 검증용)
# 포털 승인 후 프로덕션 URL로 교체
_PROD_BASE  = "https://openapi.krx.co.kr"
_DEBUG_BASE = "https://data-dbg.krx.co.kr"


class KRXClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        debug: bool = False,
    ) -> None:
        self._api_key = api_key or os.environ["KRX_API_KEY"]
        self._base = base_url or (os.environ.get("KRX_BASE_URL") or
                                   (_DEBUG_BASE if debug else _PROD_BASE))
        self._session = requests.Session()
        self._session.headers.update({
            "apikey": self._api_key,
            "User-Agent": "nautilus-quant/1.0",
        })

    def _get(self, path: str, params: dict) -> list[dict]:
        resp = self._session.get(f"{self._base}/svc/apis/{path}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("respCode") not in (None, "200", 200):
            raise RuntimeError(f"KRX error: {data}")
        # 응답 구조: {"OutBlock_1": [{...}]} 또는 직접 list
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
        return self._get(path, {"basDd": bas_dd})

    def get_stock_base_info(self, market: str = "KOSPI") -> list[dict]:
        """종목 기본정보 (시가총액, 상장주수 등). market: 'KOSPI' | 'KOSDAQ'"""
        path = "sto/stk_isu_base_info" if market.upper() == "KOSPI" else "sto/ksq_isu_base_info"
        today = date.today().strftime("%Y%m%d")
        return self._get(path, {"basDd": today})

    # ── 아래는 서비스 구독 승인 후 활성화되는 엔드포인트 (경로 미확정) ──────

    def get_derivatives_daily(self, bas_dd: str, kind: str = "futures") -> list[dict]:
        """선물/옵션 일별 매매정보 (구독 필요). kind: 'futures' | 'options'"""
        path = "drv/non_stk_fut_dd_trd" if kind == "futures" else "drv/non_stk_opt_dd_trd"
        return self._get(path, {"basDd": bas_dd})

    def get_etf_daily(self, bas_dd: str) -> list[dict]:
        """ETF 일별 매매정보 (구독 필요)."""
        return self._get("etf/etf_pd_dd_trd", {"basDd": bas_dd})

    def get_short_selling(self, bas_dd: str) -> list[dict]:
        """공매도 현황 (구독 필요)."""
        return self._get("srt/short_oview", {"basDd": bas_dd})

    def get_investor_trading(self, bas_dd: str) -> list[dict]:
        """투자자별 거래실적 (구독 필요) - 외국인/기관/개인."""
        return self._get("inv/stk_by_invsr", {"basDd": bas_dd})

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


# 구독 신청 가이드
SUBSCRIPTION_GUIDE = """
KRX OpenAPI 서비스 구독 신청 방법:
1. https://openapi.krx.co.kr → 로그인
2. 마이페이지 → 서비스 구독 신청
3. 필요 서비스 체크:
   - [필수] 지수 일별시세 (idx/kospi_dd_trd, idx/kosdaq_dd_trd)
   - [필수] 주식 종목기본정보 (sto/stk_isu_base_info, sto/ksq_isu_base_info)
   - [권장] 파생상품 일별매매 (선물/옵션)
   - [권장] ETF 일별매매
   - [권장] 공매도 현황
   - [권장] 투자자별 거래실적 (외국인/기관/개인)
4. 승인 후 프로덕션 BASE_URL 수령 → .env KRX_BASE_URL에 입력
"""
