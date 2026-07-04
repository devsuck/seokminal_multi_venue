"""SEC EDGAR Form 4 insider transaction fetcher (공개 API, 키 불필요).

공식 SEC EDGAR 데이터 엔드포인트:
- company_tickers.json: ticker → CIK 매핑
- submissions/CIK{:010d}.json: 회사별 전체 공시 목록
- Archives/{CIK}/{accession}/: 실제 Form 4 XML

오픈마켓 매수(거래코드 P)만 추출 → {ticker, date, shares, price, filer_title}.
캐시: data/form4/{ticker}.json (1일 TTL).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta

import requests

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "form4")
_HEADERS = {"User-Agent": "seokminal-research research@seokminal.local"}
_TIMEOUT = 15
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"


def _get(url: str, **kwargs) -> requests.Response:
    time.sleep(0.12)  # SEC rate limit: ≤10 req/s
    return requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, **kwargs)


# ---------- CIK lookup ----------

_cik_cache: dict[str, int] = {}


def ticker_to_cik(ticker: str) -> int | None:
    global _cik_cache
    if not _cik_cache:
        try:
            data = _get(_TICKERS_URL).json()
            _cik_cache = {v["ticker"].upper(): v["cik_str"] for v in data.values()}
        except Exception:
            return None
    return _cik_cache.get(ticker.upper())


# ---------- Form 4 fetcher ----------

def _parse_form4_xml(xml: str) -> list[dict]:
    """Form 4 XML에서 비파생 오픈마켓 매수 추출. 단순 regex (xmltodict 불필요)."""
    transactions = []
    # nonDerivativeTransaction 블록
    for block in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", xml, re.DOTALL):
        code = (re.search(r"<transactionCode>(\w+)</transactionCode>", block) or object())
        code_val = getattr(code, "group", lambda n: None)(1) or ""
        if code_val != "P":
            continue
        d_match = re.search(r"<transactionDate>\s*<value>([\d-]+)</value>", block)
        shares_match = re.search(r"<transactionShares>\s*<value>([\d.]+)</value>", block)
        price_match = re.search(r"<transactionPricePerShare>\s*<value>([\d.]+)</value>", block)
        if not d_match:
            continue
        transactions.append({
            "date": d_match.group(1),
            "shares": float(shares_match.group(1)) if shares_match else None,
            "price": float(price_match.group(1)) if price_match else None,
        })
    return transactions


def _filer_title(xml: str) -> str:
    m = re.search(r"<officerTitle>(.*?)</officerTitle>", xml, re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    for rel in ("isDirector", "isOfficer", "isTenPercentOwner"):
        m = re.search(rf"<{rel}>\s*<value>1</value>", xml)
        if m:
            return rel.replace("is", "")
    return "insider"


def fetch_form4_events(ticker: str, max_filings: int = 100) -> list[dict]:
    """ticker의 최근 Form 4 오픈마켓 매수 이벤트 목록 (거래코드 P만)."""
    os.makedirs(STORE_DIR, exist_ok=True)
    cache_path = os.path.join(STORE_DIR, f"{ticker.upper()}.json")

    # 1일 캐시
    if os.path.exists(cache_path):
        if date.fromtimestamp(os.path.getmtime(cache_path)) >= date.today() - timedelta(days=1):
            with open(cache_path) as f:
                return json.load(f)

    cik = ticker_to_cik(ticker)
    if cik is None:
        return []

    try:
        sub = _get(_SUBMISSIONS_URL.format(cik)).json()
    except Exception:
        return []

    filings = sub.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])

    events: list[dict] = []
    count = 0
    for form, acc, fdate in zip(forms, accessions, filing_dates):
        if form != "4":
            continue
        if count >= max_filings:
            break
        count += 1
        acc_clean = acc.replace("-", "")
        # form4.xml이 표준 경로 (XBRL 기반); 없으면 .txt fallback
        for xml_url in [
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/form4.xml",
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc}.txt",
        ]:
            try:
                resp = _get(xml_url)
                if resp.status_code != 200:
                    continue
                xml = resp.text
                txns = _parse_form4_xml(xml)
                if txns:
                    filer = _filer_title(xml)
                    for t in txns:
                        events.append({
                            "ticker": ticker.upper(),
                            "disclosure_date": fdate,
                            "trade_date": t["date"],
                            "shares": t["shares"],
                            "price": t["price"],
                            "filer_title": filer,
                        })
                break
            except Exception:
                continue

    with open(cache_path, "w") as f:
        json.dump(events, f)
    return events


def load_form4_universe(tickers: list[str]) -> list[dict]:
    """여러 종목 Form 4 매수 이벤트 합산."""
    all_events: list[dict] = []
    for ticker in tickers:
        all_events.extend(fetch_form4_events(ticker))
    all_events.sort(key=lambda x: x["disclosure_date"], reverse=True)
    return all_events


# ---------- SEC quarterly bulk index ----------

def _quarterly_index_url(year: int, qtr: int) -> str:
    return f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/form.idx"


def fetch_bulk_form4_events(
    years: list[int] | None = None,
    max_per_quarter: int = 200,
    cache_file: str | None = None,
) -> list[dict]:
    """SEC 분기별 전체 공시 인덱스에서 Form 4 매수 이벤트 대량 추출.

    years: 조회 연도 리스트 (기본 2022~2025)
    max_per_quarter: 분기당 최대 Form 4 파싱 수 (속도 조절)
    """
    import random
    if years is None:
        years = list(range(2022, 2026))

    if cache_file is None:
        cache_file = os.path.join(STORE_DIR, "_bulk_events.json")

    os.makedirs(STORE_DIR, exist_ok=True)
    if os.path.exists(cache_file):
        if date.fromtimestamp(os.path.getmtime(cache_file)) >= date.today() - timedelta(days=7):
            with open(cache_file) as f:
                return json.load(f)

    # CIK → ticker 역매핑
    cik_to_ticker: dict[int, str] = {}
    try:
        data = _get(_TICKERS_URL).json()
        cik_to_ticker = {v["cik_str"]: v["ticker"].upper() for v in data.values()}
    except Exception:
        pass

    all_events: list[dict] = []

    for year in years:
        for qtr in range(1, 5):
            url = _quarterly_index_url(year, qtr)
            try:
                resp = _get(url)
                if resp.status_code != 200:
                    continue
                # 인덱스 파싱: 고정폭 텍스트
                form4_lines = []
                for line in resp.text.splitlines():
                    if "4 " in line[:20] and len(line) > 60:
                        form4_lines.append(line)
                # 랜덤 샘플 (속도)
                if len(form4_lines) > max_per_quarter:
                    form4_lines = random.sample(form4_lines, max_per_quarter)

                for line in form4_lines:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    # 마지막 컬럼이 파일경로: edgar/data/{cik}/{accession}.txt
                    filepath = parts[-1]
                    m = re.search(r"edgar/data/(\d+)/([0-9-]+)\.txt", filepath)
                    if not m:
                        continue
                    cik_str, acc = m.group(1), m.group(2)
                    cik = int(cik_str)
                    ticker = cik_to_ticker.get(cik)
                    if not ticker:
                        continue
                    # 공시일자 추출
                    fdate_m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
                    fdate = fdate_m.group(1) if fdate_m else f"{year}-01-01"

                    acc_clean = acc.replace("-", "")
                    for xml_url in [
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/form4.xml",
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc}.txt",
                    ]:
                        try:
                            xml = _get(xml_url).text
                            txns = _parse_form4_xml(xml)
                            if txns:
                                filer = _filer_title(xml)
                                for t in txns:
                                    all_events.append({
                                        "ticker": ticker,
                                        "disclosure_date": fdate,
                                        "trade_date": t["date"],
                                        "shares": t["shares"],
                                        "price": t["price"],
                                        "filer_title": filer,
                                    })
                            break
                        except Exception:
                            continue

            except Exception:
                continue

    all_events.sort(key=lambda x: x["disclosure_date"], reverse=True)
    with open(cache_file, "w") as f:
        json.dump(all_events, f)
    return all_events
