# backends/kis/client.py
import time

import requests

from backends.kis.auth import KISAuth

DAILY_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
DAILY_PRICE_TR_ID = "FHKST03010100"
DAILY_INDEX_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
DAILY_INDEX_PRICE_TR_ID = "FHPUP02120000"
PAGE_SIZE = 100


class KISClient:
    """Synchronous client for KIS domestic-stock market-data endpoints."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        auth: KISAuth | None = None,
        base_url: str = "https://openapi.koreainvestment.com:9443",
        session: requests.Session | None = None,
        request_delay_seconds: float = 0.05,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url
        self._session = session or requests.Session()
        self._auth = auth or KISAuth(app_key, app_secret, base_url, self._session)
        self._request_delay_seconds = request_delay_seconds

    def get_daily_price(self, code: str, start: str, end: str) -> list[dict]:
        all_rows: list[dict] = []
        window_end = end

        while True:
            page = self._fetch_page(code, start, window_end)
            if not page:
                break

            all_rows.extend(page)

            oldest_date_in_page = page[0]["stck_bsop_date"]
            if len(page) < PAGE_SIZE or oldest_date_in_page <= start:
                break

            window_end = _previous_day(oldest_date_in_page)
            time.sleep(self._request_delay_seconds)

        all_rows.sort(key=lambda row: row["stck_bsop_date"])
        return [row for row in all_rows if start <= row["stck_bsop_date"] <= end]

    def _fetch_page(self, code: str, start: str, end: str) -> list[dict]:
        try:
            response = self._request_page(code, start, end)
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 401:
                raise
            self._auth.invalidate()
            response = self._request_page(code, start, end)

        payload = response.json()
        rt_cd = payload.get("rt_cd")
        if rt_cd != "0":
            raise RuntimeError(f"KIS API error rt_cd={rt_cd}: {payload.get('msg1')}")
        rows = payload.get("output2", [])
        non_blank = [row for row in rows if row.get("stck_bsop_date")]
        non_blank.sort(key=lambda row: row["stck_bsop_date"])
        return non_blank

    def _request_page(self, code: str, start: str, end: str) -> requests.Response:
        token = self._auth.get_access_token()
        response = self._session.get(
            f"{self._base_url}{DAILY_PRICE_PATH}",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": DAILY_PRICE_TR_ID,
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start,
                "FID_INPUT_DATE_2": end,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        response.raise_for_status()
        return response

    def get_daily_index_price(self, index_code: str, start: str, end: str) -> list[dict]:
        all_rows: list[dict] = []
        window_end = end

        while True:
            page = self._fetch_index_page(index_code, start, window_end)
            if not page:
                break

            all_rows.extend(page)

            oldest_date_in_page = page[0]["stck_bsop_date"]
            if len(page) < PAGE_SIZE or oldest_date_in_page <= start:
                break

            window_end = _previous_day(oldest_date_in_page)
            time.sleep(self._request_delay_seconds)

        all_rows.sort(key=lambda row: row["stck_bsop_date"])
        return [row for row in all_rows if start <= row["stck_bsop_date"] <= end]

    def _fetch_index_page(self, index_code: str, start: str, end: str) -> list[dict]:
        try:
            response = self._request_index_page(index_code, start, end)
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 401:
                raise
            self._auth.invalidate()
            response = self._request_index_page(index_code, start, end)

        payload = response.json()
        rt_cd = payload.get("rt_cd")
        if rt_cd != "0":
            raise RuntimeError(f"KIS API error rt_cd={rt_cd}: {payload.get('msg1')}")
        rows = payload.get("output2", [])
        non_blank = [row for row in rows if row.get("stck_bsop_date")]
        non_blank.sort(key=lambda row: row["stck_bsop_date"])
        return non_blank

    def _request_index_page(self, index_code: str, start: str, end: str) -> requests.Response:
        token = self._auth.get_access_token()
        response = self._session.get(
            f"{self._base_url}{DAILY_INDEX_PRICE_PATH}",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": DAILY_INDEX_PRICE_TR_ID,
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": index_code,
                # Index endpoint inverts the stock endpoint's convention:
                # DATE_1 is the anchor/latest date (paginated backward from
                # it), DATE_2 is the lower bound. Confirmed live against
                # the real KIS API -- don't "fix" this back to DATE_1=start
                # by analogy with get_daily_price.
                "FID_INPUT_DATE_1": end,
                "FID_INPUT_DATE_2": start,
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        response.raise_for_status()
        return response



def _previous_day(date_str: str) -> str:
    import datetime as dt

    day = dt.datetime.strptime(date_str, "%Y%m%d")
    return (day - dt.timedelta(days=1)).strftime("%Y%m%d")
