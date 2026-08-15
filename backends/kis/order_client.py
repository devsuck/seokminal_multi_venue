import requests

from backends.kis.auth import KISAuth

ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
ORDER_INQUIRE_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
ORDER_CANCEL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"

BUY_TR_ID = "VTTC0802U"
SELL_TR_ID = "VTTC0801U"
INQUIRE_TR_ID = "VTTC8001R"
CANCEL_TR_ID = "VTTC0803U"
BALANCE_TR_ID = "VTTC8434R"  # mock; real = TTTC8434R

ORDER_DIVISION_CODES = {"LIMIT": "00", "MARKET": "01"}


class KISOrderClient:
    """Client for KIS mock-trading (모의투자) order placement, query, and cancel."""

    MOCK_URL = "https://openapivts.koreainvestment.com:29443"
    REAL_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        cano: str,
        acnt_prdt_cd: str,
        auth: KISAuth | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        mock: bool = True,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._cano = cano
        self._acnt_prdt_cd = acnt_prdt_cd
        self._mock = mock
        # TR ids differ only by prefix: V=모의(mock), T=실전(real).
        self._base_url = base_url or (self.MOCK_URL if mock else self.REAL_URL)
        self._session = session or requests.Session()
        self._auth = auth or KISAuth(app_key, app_secret, self._base_url, self._session)

    def _tr(self, mock_tr_id: str) -> str:
        """Map a mock TR id (V…) to real (T…) when live."""
        return mock_tr_id if self._mock else "T" + mock_tr_id[1:]

    def place_order(
        self,
        code: str,
        side: str,
        quantity: int,
        order_division: str,
        price: int | None = None,
    ) -> dict:
        tr_id = self._tr(BUY_TR_ID if side == "BUY" else SELL_TR_ID)
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
        order_id = payload["output"]["ODNO"]  # fail loud if the order number is missing
        return {"order_id": order_id, "status": "SUBMITTED", "filled": 0.0, "remaining": float(quantity)}

    def get_order_status(self, order_date: str, order_no: str) -> dict | None:
        payload = self._call(
            "GET",
            ORDER_INQUIRE_PATH,
            self._tr(INQUIRE_TR_ID),
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
                return self._row_to_status_dict(row)
        return None

    def cancel_order(self, order_no: str, code: str, quantity: int) -> dict:
        # Does not delegate to get_order_status: confirmed live against a
        # real mock-trading account (2026-06-23) that inquire-daily-ccld
        # returns an empty output1 for this account regardless of CCLD_DVSN/
        # PDNO combination tried, even though the order genuinely exists
        # (output2.tot_ord_qty reflected it) and cancels successfully. This
        # looks like a mock-trading-environment limitation in querying
        # unfilled orders, not a bug in our request — revisit when wiring up
        # real execution later, since real-account behavior is unverified
        # and may differ. The cancel call itself is confirmed working live.
        self._call(
            "POST",
            ORDER_CANCEL_PATH,
            self._tr(CANCEL_TR_ID),
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
        return {"order_id": order_no, "status": "CANCELLED", "filled": 0.0, "remaining": 0.0}

    def get_balance(self) -> dict:
        """예수금/총평가/순자산 조회 (inquire-balance). 모의: VTTC8434R."""
        payload = self._call(
            "GET", BALANCE_PATH, self._tr(BALANCE_TR_ID),
            params={
                "CANO": self._cano, "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )
        out2 = payload.get("output2") or []
        s = out2[0] if isinstance(out2, list) and out2 else {}
        return {
            "deposit": float(s.get("dnca_tot_amt", 0) or 0),    # 예수금총금액
            "total_eval": float(s.get("tot_evlu_amt", 0) or 0),  # 총평가금액
            "net_asset": float(s.get("nass_amt", 0) or 0),       # 순자산금액
        }

    def get_holdings(self) -> list[dict]:
        """보유 종목 리스트 (inquire-balance output1): 코드/수량/평단/현재가."""
        payload = self._call(
            "GET", BALANCE_PATH, self._tr(BALANCE_TR_ID),
            params={
                "CANO": self._cano, "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )
        out = []
        for r in payload.get("output1", []) or []:
            qty = float(r.get("hldg_qty", 0) or 0)
            if qty <= 0:
                continue
            out.append({
                "code": r.get("pdno", ""),
                "qty": qty,
                "avg_price": float(r.get("pchs_avg_pric", 0) or 0),
                "current": float(r.get("prpr", 0) or 0),
            })
        return out

    @staticmethod
    def _row_to_status_dict(row: dict) -> dict:
        # KIS's trading-domain endpoints (order-cash, inquire-daily-ccld,
        # order-rvsecncl) return UPPERCASE response field names, unlike the
        # quotations-domain endpoints (e.g. get_daily_price's stck_bsop_date)
        # which return lowercase — confirmed live: a real order-cash response
        # returned {"output": {"ODNO": ..., "ORD_TMD": ...}}. The exact names
        # below (TOT_CCLD_QTY/NCCS_QTY/CNCL_YN/TOT_CCLD_AMT) follow that same
        # uppercase convention but are not yet confirmed live for this
        # specific endpoint — fix here if a live inquire-daily-ccld response
        # disagrees. Also note: confirmed live (2026-06-23, see cancel_order
        # comment) that this endpoint returns an empty output1 for at least
        # one mock-trading account regardless of query params — callers must
        # treat a missing/empty result as "unknown", not "no fill".
        filled = float(row.get("TOT_CCLD_QTY", 0))
        remaining = float(row.get("NCCS_QTY", 0))
        tot_amt = float(row.get("TOT_CCLD_AMT", 0) or 0)
        avg_price = round(tot_amt / filled, 2) if filled > 0 else 0.0
        if row.get("CNCL_YN") == "Y":
            status = "CANCELLED"
        elif remaining == 0 and filled > 0:
            status = "FILLED"
        elif filled > 0:
            status = "PARTIAL"
        else:
            status = "OPEN"
        return {"order_id": row.get("ODNO"), "status": status, "filled": filled,
                "remaining": remaining, "avg_price": avg_price}

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
