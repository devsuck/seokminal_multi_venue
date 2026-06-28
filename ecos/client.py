"""ECOS (한국은행 경제통계시스템) API client."""
import os
import requests

BASE_URL = "https://ecos.bok.or.kr/api"

# (stat_code, item_code, cycle) stored as tuple in 'meta' key
SERIES_CATALOG: dict[str, dict] = {
    # ── 기준금리 ──────────────────────────────────────────────────
    "BOK_BASE_RATE":   {"label": "한은 기준금리",      "unit": "%",   "category": "rates",
                        "stat_code": "722Y001", "item_code": "0101000", "cycle": "M"},
    "CALL_RATE":       {"label": "콜금리(익일물)",      "unit": "%",   "category": "rates",
                        "stat_code": "721Y001", "item_code": "1010000", "cycle": "M"},
    "KTB_3Y":          {"label": "국고채 3년",          "unit": "%",   "category": "rates",
                        "stat_code": "721Y001", "item_code": "5020000", "cycle": "M"},
    "KTB_10Y":         {"label": "국고채 10년",         "unit": "%",   "category": "rates",
                        "stat_code": "721Y001", "item_code": "5050000", "cycle": "M"},
    # ── 물가 ──────────────────────────────────────────────────────
    "CPI":             {"label": "소비자물가지수",      "unit": "idx", "category": "macro",
                        "stat_code": "901Y009", "item_code": "0",       "cycle": "M"},
    # ── 국민계정 ──────────────────────────────────────────────────
    "REAL_GDP":        {"label": "실질 GDP (계절조정)", "unit": "10억원","category": "macro",
                        "stat_code": "200Y104", "item_code": "10101",   "cycle": "Q"},
    # ── 고용 ──────────────────────────────────────────────────────
    "UNEMP_RATE":      {"label": "실업률",              "unit": "%",   "category": "macro",
                        "stat_code": "901Y027", "item_code": "I61BC",   "cycle": "M"},
    # ── 환율 ──────────────────────────────────────────────────────
    "KRW_USD":         {"label": "원/달러 환율",        "unit": "KRW", "category": "fx",
                        "stat_code": "731Y004", "item_code": "0000001", "cycle": "M"},
    "KRW_JPY":         {"label": "원/엔(100엔)",        "unit": "KRW", "category": "fx",
                        "stat_code": "731Y004", "item_code": "0000002", "cycle": "M"},
    # ── 통화 ──────────────────────────────────────────────────────
    "M2":              {"label": "M2 (평잔, 원계열)",   "unit": "10억원","category": "macro",
                        "stat_code": "101Y004", "item_code": "BBKA00",  "cycle": "M"},
    # ── 주가 ──────────────────────────────────────────────────────
    "KOSPI":           {"label": "KOSPI 종가",          "unit": "pts", "category": "market",
                        "stat_code": "901Y014", "item_code": "1070000", "cycle": "M"},
    "KOSDAQ":          {"label": "KOSDAQ 종가",         "unit": "pts", "category": "market",
                        "stat_code": "901Y014", "item_code": "2070000", "cycle": "M"},
    # ── 무역 ──────────────────────────────────────────────────────
    "EXPORT_IDX":      {"label": "수출금액지수",        "unit": "idx", "category": "trade",
                        "stat_code": "403Y001", "item_code": "I",       "cycle": "M"},
    "IMPORT_IDX":      {"label": "수입금액지수",        "unit": "idx", "category": "trade",
                        "stat_code": "403Y003", "item_code": "I",       "cycle": "M"},
}


class ECOSClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ["ECOS_API_KEY"]
        self._session = requests.Session()

    def get_series_by_id(self, series_id: str, start: str, end: str) -> list[dict]:
        meta = SERIES_CATALOG[series_id]
        return self.get_series(
            meta["stat_code"], meta["item_code"],
            meta.get("cycle", "M"), start, end,
        )

    def get_series(
        self,
        stat_code: str,
        item_code: str,
        cycle: str = "M",
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """Returns [{date: str, value: float | None}] sorted ascending."""
        start = start or "200001"
        end = end or "209912"
        url = (
            f"{BASE_URL}/StatisticSearch"
            f"/{self._api_key}/json/kr/1/10000"
            f"/{stat_code}/{cycle}/{start}/{end}/{item_code}"
        )
        resp = self._session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        rows = data.get("StatisticSearch", {}).get("row", [])

        result = []
        for row in rows:
            raw = row.get("DATA_VALUE", "")
            value = None if raw in ("", "-", "N/A") else _parse_float(raw)
            result.append({"date": row.get("TIME", ""), "value": value})
        result.sort(key=lambda x: x["date"])
        return result

    def catalog(self) -> dict:
        return SERIES_CATALOG


def _parse_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, TypeError):
        return None
