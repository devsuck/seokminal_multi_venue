"""금융위원회 기업재무정보 API client (data.go.kr / 15043459).

Endpoint: GET /1160100/service/GetFinaStatInfoService_V2/getSummFinaStat_V2
Params: serviceKey, crno (법인등록번호), bizYear, fnclDcd (110=연결, 120=별도)
"""
import os
import requests

BASE_URL = "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2/getSummFinaStat_V2"

# 주요 KOSPI/KOSDAQ 종목 법인등록번호 (crno) 매핑
# 법인등록번호는 변하지 않는 고정값
STOCK_CRNO_MAP: dict[str, str] = {
    # API 직접 검증 완료
    "005930": "1301110006246",  # 삼성전자 (2023: 258조)
    "005380": "1101110085450",  # 현대차 (2023: 162조)
    "000270": "1101110037998",  # 기아 (2023: 99.8조)
    "066570": "1101112487050",  # LG전자 (2023: 84.2조)
    "051910": "1101110215536",  # LG화학 (2023: 59.3조)
    "006400": "1101110192180",  # 삼성SDI (2023: 20.6조)
    "035420": "1101110003098",  # NAVER (2023: 8조)
    "105560": "1101110002959",  # KB금융 (2023: 53.1조)
    # 아래는 미검증 — 필요시 ingest.py crno-add 명령으로 추가
    # "000660": "",             # SK하이닉스 (FSC DB에서 crno 미확인)
    # "055550": "",             # 신한지주
    # "005490": "",             # POSCO홀딩스
}

# 재무제표 구분
FNCL_DCD_CONSOLIDATED = "110"  # 연결
FNCL_DCD_SEPARATE = "120"      # 별도


class CorpFinanceClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ["DATA_GO_KR_API_KEY"]
        self._session = requests.Session()

    def get_summary(
        self,
        crno: str,
        biz_year: str,
        fncl_dcd: str = FNCL_DCD_CONSOLIDATED,
    ) -> dict | None:
        """특정 연도 요약재무제표 1건 반환 (없으면 None)."""
        items = self._fetch(crno=crno, biz_year=biz_year)
        for item in items:
            if item.get("fnclDcd") == fncl_dcd:
                return item
        return items[0] if items else None

    def get_multiyear(
        self,
        crno: str,
        start_year: int,
        end_year: int,
        fncl_dcd: str = FNCL_DCD_CONSOLIDATED,
    ) -> list[dict]:
        """여러 연도 재무데이터 리스트 반환 (연도 오름차순)."""
        results = []
        for yr in range(start_year, end_year + 1):
            item = self.get_summary(crno, str(yr), fncl_dcd)
            if item:
                results.append(item)
        return results

    def _fetch(self, crno: str, biz_year: str) -> list[dict]:
        resp = self._session.get(
            BASE_URL,
            params={
                "serviceKey": self._api_key,
                "pageNo": 1,
                "numOfRows": 10,
                "resultType": "json",
                "crno": crno,
                "bizYear": biz_year,
            },
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json().get("response", {}).get("body", {})
        items_raw = body.get("items", {}).get("item", [])
        if isinstance(items_raw, dict):
            items_raw = [items_raw]
        return items_raw

    @staticmethod
    def crno_for(stock_code: str) -> str | None:
        return STOCK_CRNO_MAP.get(stock_code)

    @staticmethod
    def add_crno(stock_code: str, crno: str) -> None:
        STOCK_CRNO_MAP[stock_code] = crno

    @staticmethod
    def stock_crno_catalog() -> dict[str, str]:
        return dict(STOCK_CRNO_MAP)


def parse_financials(item: dict) -> dict:
    """API 응답 item → 계산된 재무지표 dict 반환."""
    def _int(v: str | None) -> int:
        try:
            return int(v or 0)
        except (ValueError, TypeError):
            return 0

    def _float(v: str | None) -> float:
        try:
            return float(v or 0)
        except (ValueError, TypeError):
            return 0.0

    sale = _int(item.get("enpSaleAmt"))
    op_profit = _int(item.get("enpBzopPft"))
    net_profit = _int(item.get("enpCrtmNpf"))
    total_assets = _int(item.get("enpTastAmt"))
    total_debt = _int(item.get("enpTdbtAmt"))
    total_equity = _int(item.get("enpTcptAmt"))
    paid_in_capital = _int(item.get("enpCptlAmt"))

    return {
        "biz_year": item.get("bizYear"),
        "report_type": item.get("fnclDcdNm"),
        "currency": item.get("curCd", "KRW"),
        # 규모 (원)
        "sale_amt": sale,
        "op_profit": op_profit,
        "net_profit": net_profit,
        "total_assets": total_assets,
        "total_debt": total_debt,
        "total_equity": total_equity,
        "paid_in_capital": paid_in_capital,
        # 파생 지표
        "op_margin_pct": round(op_profit / sale * 100, 2) if sale else None,
        "net_margin_pct": round(net_profit / sale * 100, 2) if sale else None,
        "roe_pct": round(net_profit / total_equity * 100, 2) if total_equity else None,
        "debt_ratio_pct": _float(item.get("fnclDebtRto")),
        # PER/PBR은 시가총액 있어야 계산 가능 → 별도 계산
    }
