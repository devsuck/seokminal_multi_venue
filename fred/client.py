"""FRED API v2 client — fetches economic time series data."""
import os
import requests

BASE_URL = "https://api.stlouisfed.org/fred"

# Curated series with labels and descriptions
SERIES_CATALOG: dict[str, dict] = {
    "DGS10":    {"label": "10Y Treasury Yield",       "unit": "%",   "category": "rates"},
    "DGS2":     {"label": "2Y Treasury Yield",        "unit": "%",   "category": "rates"},
    "DGS1MO":   {"label": "1M Treasury Yield",        "unit": "%",   "category": "rates"},
    "T10Y2Y":   {"label": "10Y-2Y Yield Spread",      "unit": "%",   "category": "rates"},
    "FEDFUNDS":  {"label": "Fed Funds Rate",           "unit": "%",   "category": "rates"},
    "CPIAUCSL": {"label": "CPI (YoY Inflation)",      "unit": "idx", "category": "macro"},
    "PCEPI":    {"label": "PCE Price Index",          "unit": "idx", "category": "macro"},
    "UNRATE":   {"label": "Unemployment Rate",        "unit": "%",   "category": "macro"},
    "GDP":      {"label": "US GDP",                   "unit": "$B",  "category": "macro"},
    "GDPC1":    {"label": "Real GDP (Chained)",       "unit": "$B",  "category": "macro"},
    "VIXCLS":   {"label": "CBOE VIX",                "unit": "pts", "category": "volatility"},
    "BAMLH0A0HYM2": {"label": "HY Credit Spread",    "unit": "%",   "category": "credit"},
    "DTWEXBGS": {"label": "USD Index (Broad)",        "unit": "idx", "category": "fx"},
    "M2SL":     {"label": "M2 Money Supply",          "unit": "$B",  "category": "macro"},
}


class FREDClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ["FRED_API_KEY"]
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self._api_key}"

    def get_series(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """Returns [{date: str, value: float | None}] sorted ascending."""
        params: dict = {"series_id": series_id, "file_type": "json", "api_key": self._api_key}
        if start:
            params["observation_start"] = start
        if end:
            params["observation_end"] = end

        resp = self._session.get(f"{BASE_URL}/series/observations", params=params)
        resp.raise_for_status()
        data = resp.json()

        observations = data.get("observations", [])
        result = []
        for obs in observations:
            raw_val = obs.get("value", ".")
            value = None if raw_val in (".", "") else float(raw_val)
            result.append({"date": obs["date"], "value": value})
        return result

    def get_series_info(self, series_id: str) -> dict:
        params = {"series_id": series_id, "file_type": "json", "api_key": self._api_key}
        resp = self._session.get(f"{BASE_URL}/series", params=params)
        resp.raise_for_status()
        serieses = resp.json().get("seriess", [])
        return serieses[0] if serieses else {}

    def catalog(self) -> dict:
        return SERIES_CATALOG
