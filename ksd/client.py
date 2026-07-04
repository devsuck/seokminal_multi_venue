"""KSD (한국예탁결제원) / 금융위원회 data.go.kr API 클라이언트.

환경변수:
  DATA_GO_KR_API_KEY   — 공통 키 (기업재무정보와 동일 키)
  DATA_GO_KR_KSD_KEY   — KSD 전용 키 (별도 발급 시 우선 사용)

확인된 엔드포인트 (swagger 기반 / 2026-06-26):
  배당정보: 1160100/GetStocDiviInfoService_V2/getDiviInfo_V2
  대차순위: 1160100/GetStocLendBorrInfoService_V2/getStLendAndBorrItemRank_V2
  권리일정: 1160100/GetStocRighScheService_V2/getRighExerReasSche_V2
  발행정보: 1160100/GetStocIssuInfoService_V3/getStocIssuInfo_V3
"""
from __future__ import annotations

import os
import time
import requests

_BASE = "https://apis.data.go.kr/1160100"

# (service, operation)
_ENDPOINTS: dict[str, tuple[str, str]] = {
    "div_info":      ("GetStocDiviInfoService_V2",     "getDiviInfo_V2"),
    "borrow_rank":   ("GetStocLendBorrInfoService_V2", "getStLendAndBorrItemRank_V2"),
    "borrow_status": ("GetStocLendBorrInfoService_V2", "getStItemLendAndBorrStatu_V2"),
    "rights_sched":  ("GetStocRighScheService_V2",     "getRighExerReasSche_V2"),
    "issue_info":    ("GetStocIssuInfoService_V3",     "getStocIssuInfo_V3"),
}


def isin_from_code(code: str) -> str:
    """6자리 종목코드 → 12자리 ISIN(보통주 KR7). 이미 12자리면 그대로.

    체크디짓은 ISIN 표준(문자→숫자 변환 후 Luhn)으로 계산 —
    종목마다 다르므로 '3' 하드코딩 금지(예: 138040 → KR7138040001).
    """
    if len(code) == 12:
        return code
    base = f"KR7{code}00"
    digits = "".join(str(int(ch, 36)) for ch in base)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return base + str((10 - total % 10) % 10)


class KSDClient:
    def __init__(
        self,
        api_key: str | None = None,
        throttle_s: float = 0.15,
    ) -> None:
        self._key = (
            api_key
            or os.environ.get("DATA_GO_KR_KSD_KEY")
            or os.environ.get("DATA_GO_KR_API_KEY")
        )
        if not self._key:
            raise KeyError("DATA_GO_KR_KSD_KEY or DATA_GO_KR_API_KEY not set")
        self._throttle = throttle_s
        self._last = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "seokminal research bot"

    def _get(self, endpoint_key: str, params: dict) -> list[dict]:
        svc, op = _ENDPOINTS[endpoint_key]
        url = f"{_BASE}/{svc}/{op}"

        elapsed = time.time() - self._last
        if elapsed < self._throttle:
            time.sleep(self._throttle - elapsed)

        r = self._session.get(
            url,
            params={"serviceKey": self._key, "resultType": "json",
                    "pageNo": "1", "numOfRows": "100", **params},
            timeout=20,
        )
        self._last = time.time()
        r.raise_for_status()

        data = r.json()
        rc = data.get("response", {}).get("header", {}).get("resultCode", "")
        if rc not in ("", "00", "000"):
            raise RuntimeError(f"API error {rc}: {data}")

        body = data.get("response", {}).get("body", {})
        items = body.get("items", {})
        if not items:
            return []
        if isinstance(items, dict):
            item = items.get("item", [])
            return item if isinstance(item, list) else [item]
        if isinstance(items, list):
            return items
        return []

    # ── 주식 배당정보 ─────────────────────────────────────────────────────────────
    # 주요 응답 필드:
    #   isinCd, stckIssuCmpyNm, dvdnBasDt (배당기준일),
    #   cashDvdnPayDt (현금배당지급일), stckHndvDt (주식교부일),
    #   stckGenrDvdnAmt (주당배당금), stckGenrCashDvdnRt (현금배당률),
    #   stckDvdnRcd/Nm (배당사유코드), scrsItmsKcd/Nm (주식종류코드)

    def get_dividend(
        self,
        isin_cd: str | None = None,
        begin_dt: str | None = None,
        end_dt: str | None = None,
        bas_dt: str | None = None,
    ) -> list[dict]:
        """주식 배당정보 조회. isin_cd OR bas_dt 중 하나 이상 필요."""
        params: dict = {}
        if isin_cd:
            params["isinCd"] = isin_from_code(isin_cd)
        if bas_dt:
            params["basDt"] = bas_dt
        if begin_dt:
            params["beginBasDt"] = begin_dt
        if end_dt:
            params["endBasDt"] = end_dt
        return self._get("div_info", params)

    def get_dividend_by_date(self, bas_dt: str) -> list[dict]:
        """기준일 기준 전체 종목 배당 조회."""
        return self._get("div_info", {"basDt": bas_dt})

    # ── 주식 대차정보 ─────────────────────────────────────────────────────────────
    # 주요 응답 필드:
    #   isinCd, isinCdNm, basDt,
    #   lnbCclStckCnt (대차체결주식수), rcalRdptStckCnt (리콜상환주식수),
    #   rdptStckCnt (상환주식수), lnbRmanStckCnt (대차잔여주식수), lnbBal (대차잔액)

    def get_borrowing_rank(self, bas_dt: str, top_n: int = 50) -> list[dict]:
        """대차 종목 순위 (대차잔고 기준). top_n: 상위 N개."""
        rows = self._get("borrow_rank", {"basDt": bas_dt, "numOfRows": str(top_n)})
        return rows[:top_n]

    def get_borrowing_status(self, bas_dt: str, isin_cd: str | None = None) -> list[dict]:
        """종목별 대차현황. isin_cd 없으면 전체."""
        params: dict = {"basDt": bas_dt}
        if isin_cd:
            params["isinCd"] = isin_from_code(isin_cd)
        return self._get("borrow_status", params)

    # ── 주식 권리일정 ─────────────────────────────────────────────────────────────
    # 주요 응답 필드:
    #   basDt, crno, stckIssuCmpyNm, stckIssuRcd/Nm (발행사유코드),
    #   rgtExertRcd/Nm (권리행사사유코드), rgtExertSttgDt/EdDt (권리행사기간),
    #   nmlsLckSttgDt/EdDt (명부폐쇄기간)

    def get_rights_schedule(
        self,
        bas_dt: str | None = None,
        begin_dt: str | None = None,
        end_dt: str | None = None,
        crno: str | None = None,
    ) -> list[dict]:
        """권리행사사유별 일정 조회.

        isinCd는 이 API의 필터 파라미터가 아님 (crno 또는 basDt 사용).
        """
        params: dict = {}
        if bas_dt:
            params["basDt"] = bas_dt
        if begin_dt:
            params["beginBasDt"] = begin_dt
        if end_dt:
            params["endBasDt"] = end_dt
        if crno:
            params["crno"] = crno
        return self._get("rights_sched", params)

    # ── 주식 발행정보 ─────────────────────────────────────────────────────────────

    def get_issuance(self, isin_cd: str | None = None, bas_dt: str | None = None) -> list[dict]:
        """주식 발행정보 (발행주식수, 보호예수 등)."""
        params: dict = {}
        if isin_cd:
            params["isinCd"] = isin_from_code(isin_cd)
        if bas_dt:
            params["basDt"] = bas_dt
        return self._get("issue_info", params)
