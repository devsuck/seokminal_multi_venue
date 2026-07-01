"""SEC EDGAR Form 4 client for US insider trading disclosures."""
from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

import requests

EDGAR_BASE = "https://data.sec.gov"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
_HEADERS = {"User-Agent": "seokminal-dashboard contact@seokminal.dev"}
_TIMEOUT = 15
_MAX_RESULTS = 50


@lru_cache(maxsize=1)
def _ticker_cik_map() -> dict[str, str]:
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return {
        v["ticker"].upper(): str(v["cik_str"]).zfill(10)
        for v in r.json().values()
    }


def ticker_to_cik(ticker: str) -> str | None:
    return _ticker_cik_map().get(ticker.upper())


def get_form4_transactions(ticker: str, days: int = 90) -> list[dict]:
    """
    Fetch and parse recent Form 4 filings for a US ticker.
    Returns list of transaction dicts.
    """
    cik = ticker_to_cik(ticker)
    if not cik:
        return []

    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    subs_r = requests.get(
        f"{EDGAR_BASE}/submissions/CIK{cik}.json",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    subs_r.raise_for_status()
    subs = subs_r.json()

    recent = subs["filings"]["recent"]
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])

    results: list[dict] = []
    cik_int = int(cik)

    for form, date, acc in zip(forms, dates, accessions):
        if form != "4":
            continue
        if date < cutoff:
            break  # sorted newest-first, so we can break early
        if len(results) >= _MAX_RESULTS:
            break

        txns = _fetch_filing_transactions(cik_int, acc, date, ticker)
        results.extend(txns)

    return results[:_MAX_RESULTS]


def _fetch_filing_transactions(
    cik_int: int, accession: str, filing_date: str, ticker: str
) -> list[dict]:
    acc_clean = accession.replace("-", "")
    # Try to find the primary Form 4 XML document via the index
    try:
        idx_url = f"{EDGAR_ARCHIVES}/{cik_int}/{acc_clean}/index.json"
        idx_r = requests.get(idx_url, headers=_HEADERS, timeout=10)
        if not idx_r.ok:
            return []
        idx = idx_r.json()
        items = idx.get("directory", {}).get("item", [])
        xml_name = next(
            (
                f["name"]
                for f in items
                if f["name"].lower().endswith(".xml")
                and "index" not in f["name"].lower()
                and f["name"].lower() != "form4.xml"  # prefer non-generic
            ),
            next(
                (f["name"] for f in items if f["name"].lower().endswith(".xml")),
                None,
            ),
        )
        if not xml_name:
            return []
        xml_url = f"{EDGAR_ARCHIVES}/{cik_int}/{acc_clean}/{xml_name}"
        xml_r = requests.get(xml_url, headers=_HEADERS, timeout=10)
        if not xml_r.ok:
            return []
        return _parse_form4(xml_r.text, filing_date, ticker)
    except Exception:
        return []


def _text(el, path: str) -> str | None:
    node = el.find(path)
    if node is None:
        return None
    val = node.find("value")
    return (val.text or "").strip() if val is not None else (node.text or "").strip() or None


def _parse_form4(xml_text: str, filing_date: str, issuer_ticker: str) -> list[dict]:
    results: list[dict] = []
    try:
        root = ET.fromstring(xml_text)

        reporter = (
            _text(root, ".//reportingOwnerId/rptOwnerName")
            or _text(root, ".//rptOwnerName")
            or "Unknown"
        )
        issuer = _text(root, ".//issuerName") or issuer_ticker
        ticker = _text(root, ".//issuerTradingSymbol") or issuer_ticker

        for txn in root.findall(".//nonDerivativeTransaction"):
            date_val = _text(txn, ".//transactionDate") or filing_date
            code = _text(txn, ".//transactionCode") or ""
            shares_str = _text(txn, ".//transactionShares")
            price_str = _text(txn, ".//transactionPricePerShare")
            owned_str = _text(txn, ".//sharesOwnedFollowingTransaction")

            try:
                shares = float(shares_str) if shares_str else None
            except ValueError:
                shares = None
            try:
                price = float(price_str) if price_str else None
            except ValueError:
                price = None
            try:
                owned = float(owned_str) if owned_str else None
            except ValueError:
                owned = None

            # P=Purchase, S=Sale, A=Grant/Award, D=Disposition, F=Tax withhold
            if code in ("P", "S"):  # only open-market buys/sells
                results.append({
                    "filing_date": filing_date,
                    "transaction_date": date_val,
                    "reporter": reporter,
                    "ticker": ticker,
                    "issuer": issuer,
                    "transaction_code": code,
                    "trade_type": "BUY" if code == "P" else "SELL",
                    "shares": shares,
                    "price_per_share": price,
                    "value_usd": shares * price if shares and price else None,
                    "shares_owned_after": owned,
                })
    except ET.ParseError:
        pass
    return results


# ── Recent feed (all companies) ────────────────────────────────────────────────

_SEARCH_BASE = "https://efts.sec.gov/LATEST/search-index"


def get_recent_form4_feed(days: int = 7, max_filings: int = 40) -> list[dict]:
    """
    Fetch recent Form 4 P/S transactions across all companies via EDGAR full-text search.
    Parses up to max_filings filings in parallel.
    """
    end_dt = datetime.date.today()
    start_dt = end_dt - datetime.timedelta(days=days)

    r = requests.get(
        _SEARCH_BASE,
        params={
            "forms": "4",
            "dateRange": "custom",
            "startdt": start_dt.isoformat(),
            "enddt": end_dt.isoformat(),
        },
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    hits = r.json().get("hits", {}).get("hits", [])[:max_filings]

    def _parse_hit(hit: dict) -> list[dict]:
        src = hit.get("_source", {})
        # EDGAR FTS uses 'adsh' for accession; '_id' also carries it before ':'.
        acc = src.get("adsh") or hit.get("_id", "").split(":")[0]
        file_date = src.get("file_date", "")
        # display_names: ["Reporter (CIK …)", "Issuer CORP (CIK …)"] — last = issuer
        names = src.get("display_names") or []
        entity = names[-1].split("  (")[0] if names else ""
        if not acc or not file_date:
            return []
        # Archive path CIK = accession's filer prefix.
        try:
            cik_int = int(acc.split("-")[0])
        except (ValueError, IndexError):
            return []
        txns = _fetch_filing_transactions(cik_int, acc, file_date, "")
        for t in txns:
            if not t.get("issuer"):
                t["issuer"] = entity.title()
        return txns

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_parse_hit, h): h for h in hits}
        for fut in as_completed(futures, timeout=30):
            try:
                results.extend(fut.result())
            except Exception:
                pass

    return sorted(results, key=lambda x: x.get("filing_date", ""), reverse=True)
