"""SEC EDGAR API client — free, no key required.

Endpoints used:
  company search:  https://efts.sec.gov/LATEST/search-index?q="{name}"&dateRange=custom
  company facts:   https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json
  submissions:     https://data.sec.gov/submissions/CIK{CIK10}.json

Rate limit: 10 req/s — per SEC fair-access policy.
"""
from __future__ import annotations

import re
import time
import requests
from functools import lru_cache

_FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"
_SUBS_BASE  = "https://data.sec.gov/submissions"
_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

_HEADERS = {
    "User-Agent": "seokminal research bot",
    "From": "tjrgns97502@naver.com",
    "Accept-Encoding": "gzip, deflate",
}

# 자주 쓰는 CIK 캐시
_KNOWN_CIK: dict[str, str] = {
    "AAPL":  "0000320193",
    "MSFT":  "0000789019",
    "GOOGL": "0001652044",
    "AMZN":  "0001018724",
    "META":  "0001326801",
    "NVDA":  "0001045810",
    "TSLA":  "0001318605",
    "JPM":   "0000019617",
    "BRK":   "0001067983",
    "V":     "0001403161",
    "MA":    "0001141391",
    "XOM":   "0000034088",
    "JNJ":   "0000200406",
    "WMT":   "0000104169",
    "PG":    "0000080424",
}

# US-GAAP 재무지표 → XBRL concept 매핑 (우선순위 리스트 — 첫 번째 히트 사용)
GAAP_CONCEPTS: dict[str, list[str]] = {
    "revenue":    ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "op_income":  ["OperatingIncomeLoss"],
    "total_assets": ["Assets"],
    "equity":     ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "rd_expense": ["ResearchAndDevelopmentExpense"],
    "capex":      ["PaymentsToAcquirePropertyPlantAndEquipment"],
}


class SECEdgarClient:
    def __init__(self, throttle_s: float = 0.11) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._throttle = throttle_s
        self._last_req = 0.0

    def _get(self, url: str, **kwargs) -> dict:
        elapsed = time.time() - self._last_req
        if elapsed < self._throttle:
            time.sleep(self._throttle - elapsed)
        r = self._session.get(url, timeout=15, **kwargs)
        self._last_req = time.time()
        r.raise_for_status()
        return r.json()

    @lru_cache(maxsize=128)
    def get_cik(self, ticker: str) -> str:
        """ticker → CIK 번호 (10자리 zero-padded)."""
        ticker = ticker.upper()
        if ticker in _KNOWN_CIK:
            return _KNOWN_CIK[ticker]
        # EDGAR 회사 검색
        data = self._get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": f'"{ticker}"', "dateRange": "custom",
                    "startdt": "2020-01-01", "enddt": "2024-12-31",
                    "forms": "10-K"},
        )
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits:
            src = hit.get("_source", {})
            if src.get("entity_name", "").upper().startswith(ticker[:4]):
                raw = src.get("file_num", "") or src.get("entity_id", "")
                if raw:
                    return raw.zfill(10)
        # 대안: company_tickers.json (EDGAR 공식 전체 목록)
        tickers_json = self._get("https://www.sec.gov/files/company_tickers.json")
        for _idx, item in tickers_json.items():
            if item.get("ticker", "").upper() == ticker:
                return str(item["cik_str"]).zfill(10)
        raise ValueError(f"CIK not found for ticker: {ticker}")

    def get_company_facts(self, cik: str) -> dict:
        """전체 XBRL facts (US-GAAP + DEI) — 대용량 JSON."""
        cik10 = cik.zfill(10)
        return self._get(f"{_FACTS_BASE}/CIK{cik10}.json")

    def get_concept(
        self,
        cik: str,
        concept: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
        annual_only: bool = True,
    ) -> list[dict]:
        """특정 XBRL concept 시계열 반환.

        Returns list of {end, val, form, filed, accn} sorted by end date.
        annual_only=True → 10-K (form='10-K') only.
        """
        cik10 = cik.lstrip("0").zfill(10) if not cik.startswith("CIK") else cik[3:]
        data = self._get(
            f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{concept}.json"
        )
        units_data = data.get("units", {})
        rows: list[dict] = []
        seen_end: set[str] = set()  # 중복 제거 (같은 end date, 최신 filing 유지)
        for unit_label, entries in units_data.items():
            if unit and unit.upper() not in unit_label.upper() and unit_label != "shares":
                continue
            # 가장 최신 filed 기준 정렬
            sorted_entries = sorted(entries, key=lambda e: e.get("filed", ""), reverse=True)
            for e in sorted_entries:
                if annual_only and e.get("form") not in ("10-K", "10-K/A"):
                    continue
                if "end" not in e or "val" not in e:
                    continue
                end = e["end"]
                if end in seen_end:
                    continue
                seen_end.add(end)
                rows.append({
                    "end":   end,
                    "val":   e["val"],
                    "form":  e.get("form"),
                    "filed": e.get("filed"),
                    "unit":  unit_label,
                })
        rows.sort(key=lambda x: x["end"])
        return rows

    def _get_concept_with_fallback(
        self,
        cik: str,
        concepts: list[str],
        unit: str = "USD",
        annual_only: bool = True,
    ) -> dict[str, int | float]:
        """여러 concept를 순서대로 시도, 첫 성공 concept의 {end_year: val} 반환."""
        for concept in concepts:
            try:
                rows = self.get_concept(cik, concept, unit=unit, annual_only=annual_only)
                if rows:
                    # 같은 fiscal year 중 가장 최신 val 사용
                    year_map: dict[str, int | float] = {}
                    for r in rows:
                        yr = r["end"][:4]
                        year_map[yr] = r["val"]
                    return year_map
            except Exception:
                continue
        return {}

    def get_financials(
        self,
        ticker: str,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> dict:
        """주요 재무지표 묶음 반환.

        Returns {ticker, cik, metrics: {key: [{end, val, ...}]}}
        """
        cik = self.get_cik(ticker)
        result: dict = {"ticker": ticker, "cik": cik, "metrics": {}}
        for key, concepts in GAAP_CONCEPTS.items():
            unit = "USD"
            try:
                rows = self.get_concept(cik, concepts[0], unit=unit)
                if not rows and len(concepts) > 1:
                    for alt in concepts[1:]:
                        rows = self.get_concept(cik, alt, unit=unit)
                        if rows:
                            break
                if start_year:
                    rows = [r for r in rows if int(r["end"][:4]) >= start_year]
                if end_year:
                    rows = [r for r in rows if int(r["end"][:4]) <= end_year]
                result["metrics"][key] = rows
            except Exception:
                result["metrics"][key] = []
        return result

    def get_annual_summary(
        self,
        ticker: str,
        start_year: int = 2019,
        end_year: int = 2024,
    ) -> list[dict]:
        """연도별 요약 재무제표."""
        cik = self.get_cik(ticker)
        metrics: dict[str, dict[str, int | float]] = {}
        for key, concepts in GAAP_CONCEPTS.items():
            metrics[key] = self._get_concept_with_fallback(cik, concepts)

        result = []
        for y in range(start_year, end_year + 1):
            ys = str(y)
            rev = metrics["revenue"].get(ys)
            ni  = metrics["net_income"].get(ys)
            ta  = metrics["total_assets"].get(ys)
            eq  = metrics["equity"].get(ys)
            op  = metrics["op_income"].get(ys)
            gp  = metrics["gross_profit"].get(ys)
            eps = metrics["eps_diluted"].get(ys)
            ltd = metrics["long_term_debt"].get(ys)
            if rev is None and ni is None:
                continue
            result.append({
                "year":           y,
                "revenue":        rev,
                "gross_profit":   gp,
                "op_income":      op,
                "net_income":     ni,
                "total_assets":   ta,
                "equity":         eq,
                "long_term_debt": ltd,
                "eps_diluted":    eps,
                "op_margin_pct":  round(op / rev * 100, 2) if op and rev else None,
                "net_margin_pct": round(ni / rev * 100, 2) if ni and rev else None,
                "roe_pct":        round(ni / eq * 100, 2) if ni and eq else None,
            })
        return result
