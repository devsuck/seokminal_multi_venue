"""Senate Electronic Financial Disclosure (EFD) — Periodic Transaction Reports.

무료, 키 없음. Senate EFD API + 개별 XML 파싱.
캐시: data/congress/senate_efd_*.json (연도별, 7일 TTL)

CLI: PYTHONPATH=. python3 research/data/senate_efd.py
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta

STORE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "congress",
)
_SEARCH_URL = "https://efts.senate.gov/LATEST/search-index"
_TIMEOUT = 20
_HEADERS = {"User-Agent": "research-bot/1.0 (academic)"}


def _fetch_filing_index(year: int) -> list[dict]:
    """Senate EFD 검색 API — PTR 파일링 목록."""
    import requests
    params = {
        "q": "",
        "target": "filings",
        "filingType": "PTR",
        "dateRange": "custom",
        "fromDate": f"{year}-01-01",
        "toDate": f"{year}-12-31",
        "limit": 200,
        "offset": 0,
    }
    results: list[dict] = []
    while True:
        try:
            r = requests.get(_SEARCH_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(batch)
        if len(results) >= data.get("count", 0):
            break
        params["offset"] += len(batch)
        time.sleep(0.5)
    return results


def _parse_xml_purchases(xml_text: str) -> list[dict]:
    """PTR XML 문서에서 Purchase 거래 추출."""
    purchases = []
    # XML 구조: <Transaction>...</Transaction> blocks
    tx_blocks = re.findall(r"<Transaction>(.*?)</Transaction>", xml_text, re.DOTALL)
    for block in tx_blocks:
        tx_type = re.search(r"<Type[^>]*>(.*?)</Type>", block)
        if not tx_type or "purchase" not in tx_type.group(1).lower():
            continue
        ticker_m = re.search(r"<Ticker[^>]*>(.*?)</Ticker>", block)
        tx_date_m = re.search(r"<TransactionDate[^>]*>(.*?)</TransactionDate>", block)
        amount_m = re.search(r"<Amount[^>]*>(.*?)</Amount>", block)
        if not ticker_m:
            continue
        ticker = ticker_m.group(1).strip().upper()
        if not ticker or ticker in ("N/A", "--", ""):
            continue
        purchases.append({
            "ticker": ticker,
            "trade_date": (tx_date_m.group(1).strip() if tx_date_m else ""),
            "amount_str": (amount_m.group(1).strip() if amount_m else ""),
        })
    return purchases


def _parse_html_purchases(html: str) -> list[dict]:
    """PTR HTML 문서 fallback — 테이블 파싱."""
    purchases = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) < 5:
            continue
        # 일반 PTR 구조: Date | Owner | Ticker | AssetName | AssetType | Type | Amount
        if not any("purchase" in c.lower() for c in cells):
            continue
        # ticker: 대문자 1~5자 셀 찾기
        ticker = ""
        for c in cells:
            if re.match(r"^[A-Z]{1,5}$", c.strip()):
                ticker = c.strip()
                break
        if not ticker:
            continue
        date_cell = cells[0] if cells else ""
        amount_cell = cells[-1] if cells else ""
        purchases.append({
            "ticker": ticker,
            "trade_date": date_cell,
            "amount_str": amount_cell,
        })
    return purchases


def _download_filing(filing: dict) -> list[dict]:
    """개별 PTR 파일링 다운로드 → purchases 추출."""
    import requests
    link = filing.get("direct_download_link", "")
    if not link:
        return []
    try:
        r = requests.get(link, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        text = r.text
        if "<?xml" in text or "<Report" in text:
            purchases = _parse_xml_purchases(text)
        else:
            purchases = _parse_html_purchases(text)
        reporter = filing.get("senator_name") or (
            f"{filing.get('first_name','')} {filing.get('last_name','')}".strip()
        )
        received = filing.get("date_received", "")
        for p in purchases:
            p["reporter"] = reporter
            p["disclosure_date"] = received
            p["chamber"] = "senate"
        return purchases
    except Exception:
        return []


def _cache_path(year: int) -> str:
    return os.path.join(STORE_DIR, f"senate_efd_{year}.json")


def pull_year(year: int, force: bool = False) -> list[dict]:
    """연도별 Senate PTR 매수 이벤트 풀링. 7일 캐시."""
    os.makedirs(STORE_DIR, exist_ok=True)
    cache = _cache_path(year)
    if not force and os.path.exists(cache):
        mtime = date.fromtimestamp(os.path.getmtime(cache))
        if mtime >= date.today() - timedelta(days=7):
            with open(cache) as f:
                return json.load(f)

    print(f"  Senate EFD {year}: 파일링 목록 요청...")
    filings = _fetch_filing_index(year)
    print(f"  {year}: {len(filings)}건 파일링 → 상세 다운로드")

    events: list[dict] = []
    for i, filing in enumerate(filings):
        purchases = _download_filing(filing)
        events.extend(purchases)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(filings)} 처리 ({len(events)}건 수집)")
        time.sleep(0.3)

    with open(cache, "w") as f:
        json.dump(events, f, ensure_ascii=False)
    print(f"  {year}: {len(events)}건 저장 → {cache}")
    return events


def load_events(min_date: str = "2020-01-01", years: list[int] | None = None) -> list[dict]:
    """Senate PTR BUY 이벤트 로드. min_date 이후만 반환."""
    if years is None:
        start_year = int(min_date[:4])
        years = list(range(start_year, date.today().year + 1))
    all_events: list[dict] = []
    for year in years:
        all_events.extend(pull_year(year))
    filtered = [
        e for e in all_events
        if e.get("disclosure_date", "") >= min_date and e.get("ticker")
    ]
    filtered.sort(key=lambda x: x["disclosure_date"])
    return filtered


if __name__ == "__main__":
    print("Senate EFD PTR 매수 이벤트 수집 (2022~)")
    events = load_events(min_date="2022-01-01")
    print(f"\n총 {len(events)}건")
    if events:
        print("최근 10건:")
        for e in events[-10:]:
            print(f"  {e['disclosure_date']}  {e['ticker']:6s}  {e['reporter']}")
