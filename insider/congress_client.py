"""US Congress trading (STOCK Act 공시) via FMP stable senate/house-latest.

의원 본인·배우자의 주식 매매 신고. 트럼프 개인매매/정부기관 매수는 체계적
피드가 없어 미지원 — 의회(상·하원)만 제공.
"""
import os

import requests

_BASE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 12


def _key() -> str:
    k = os.environ.get("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
    if not k:
        raise ValueError("FINANCIAL_MODELING_PREP_API_KEY not set")
    return k


def _norm(row: dict, chamber: str) -> dict:
    t = str(row.get("type", "")).lower()
    trade_type = "BUY" if "purchase" in t else "SELL" if "sale" in t or "sold" in t else "OTHER"
    name = f"{row.get('firstName','')} {row.get('lastName','')}".strip() or row.get("office", "")
    return {
        "chamber": chamber,                       # senate | house
        "trade_date": row.get("transactionDate", ""),
        "disclosure_date": row.get("disclosureDate", ""),
        "reporter": name,
        "district": row.get("district", ""),
        "owner": row.get("owner", "") or "Self",
        "ticker": row.get("symbol") or None,
        "asset": row.get("assetDescription", ""),
        "trade_type": trade_type,
        "amount": row.get("amount", ""),          # 범위 문자열 ($1,001 - $15,000)
        "link": row.get("link") or None,
    }


def get_congress_trades(limit: int = 80) -> list[dict]:
    """상·하원 최근 신고 매매 병합 (공시일 내림차순)."""
    key = _key()
    rows: list[dict] = []
    for chamber, path in (("senate", "senate-latest"), ("house", "house-latest")):
        try:
            r = requests.get(f"{_BASE}/{path}", params={"apikey": key}, timeout=_TIMEOUT)
            r.raise_for_status()
            rows.extend(_norm(x, chamber) for x in r.json())
        except Exception:
            continue
    rows.sort(key=lambda x: x.get("disclosure_date", ""), reverse=True)
    return rows[:limit]
