import requests

from backends.kis.auth import KISAuth

ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
ORDER_INQUIRE_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
ORDER_CANCEL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"

BUY_TR_ID = "VTTC0802U"
SELL_TR_ID = "VTTC0801U"
INQUIRE_TR_ID = "VTTC8001R"
CANCEL_TR_ID = "VTTC0803U"

ORDER_DIVISION_CODES = {"LIMIT": "00", "MARKET": "01"}


class KISOrderClient:
    """Client for KIS mock-trading (모의투자) order placement, query, and cancel."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        cano: str,
        acnt_prdt_cd: str,
        auth: KISAuth | None = None,
        base_url: str = "https://openapivts.koreainvestment.com:29443",
        session: requests.Session | None = None,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._cano = cano
        self._acnt_prdt_cd = acnt_prdt_cd
        self._base_url = base_url
        self._session = session or requests.Session()
        self._auth = auth or KISAuth(app_key, app_secret, base_url, self._session)

    def place_order(
        self,
        code: str,
        side: str,
        quantity: int,
        order_division: str,
        price: int | None = None,
    ) -> dict:
        tr_id = BUY_TR_ID if side == "BUY" else SELL_TR_ID
        ord_unpr = str(price) if order_division == "LIMIT" else "0"
        payload = self._call(
            "POST",
            ORDER_CASH_PATH,
            tr_id,
            json_body={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": ORDER_DIVISION_CODES[order_division],
                "ORD_QTY": str(quantity),
                "ORD_UNPR": ord_unpr,
            },
        )
        _ = payload["output"]["ODNO"]  # fail loud if the order number is missing
        return payload

    def get_order_status(self, order_date: str, order_no: str) -> dict | None:
        payload = self._call(
            "GET",
            ORDER_INQUIRE_PATH,
            INQUIRE_TR_ID,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "INQR_STRT_DT": order_date,
                "INQR_END_DT": order_date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        for row in payload.get("output1", []):
            if row.get("ODNO") == order_no:
                return row
        return None

    def cancel_order(self, order_date: str, order_no: str, code: str, quantity: int) -> dict:
        return self._call(
            "POST",
            ORDER_CANCEL_PATH,
            CANCEL_TR_ID,
            json_body={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "KRX_FWDG_ORD_ORGNO": "",
                "ORGN_ODNO": order_no,
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y",
            },
        )

    def _call(
        self,
        method: str,
        path: str,
        tr_id: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        try:
            response = self._send(method, path, tr_id, params=params, json_body=json_body)
            response.raise_for_status()
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 401:
                raise
            self._auth.invalidate()
            response = self._send(method, path, tr_id, params=params, json_body=json_body)
            response.raise_for_status()

        payload = response.json()
        if payload.get("rt_cd") != "0":
            raise RuntimeError(f"KIS API error rt_cd={payload.get('rt_cd')}: {payload.get('msg1')}")
        return payload

    def _send(
        self,
        method: str,
        path: str,
        tr_id: str,
        *,
        params: dict | None,
        json_body: dict | None,
    ) -> requests.Response:
        token = self._auth.get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
        }
        url = f"{self._base_url}{path}"
        if method == "POST":
            headers["custtype"] = "P"
            return self._session.post(url, headers=headers, json=json_body)
        return self._session.get(url, headers=headers, params=params)
