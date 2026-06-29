"""OpenDART API client for Korean insider trading disclosures."""
from __future__ import annotations

import os

import requests

DART_BASE = "https://opendart.fss.or.kr/api"
_TIMEOUT = 12


def _key() -> str:
    key = os.environ.get("OPENDART_API_KEY", "")
    if not key:
        raise ValueError("OPENDART_API_KEY not set")
    return key


def search_company(name: str) -> list[dict]:
    """Company name → list of {corp_code, corp_name, stock_code}."""
    r = requests.get(
        f"{DART_BASE}/company.json",
        params={"crtfc_key": _key(), "corp_name": name, "page_no": 1, "page_count": 20},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "000":
        return []
    return [
        {
            "corp_code": c["corp_code"],
            "corp_name": c["corp_name"],
            "stock_code": c.get("stock_code", ""),
        }
        for c in data.get("list", [])
        if c.get("stock_code")  # only listed companies
    ]


def get_executive_stock_changes(
    corp_code: str,
    bgn_de: str,
    end_de: str,
    page_count: int = 40,
) -> list[dict]:
    """
    임원·주요주주 특정증권등 소유상황보고 변동 내역.
    bgn_de / end_de: YYYYMMDD
    Returns list of trade dicts.
    """
    r = requests.get(
        f"{DART_BASE}/elestock.json",
        params={
            "crtfc_key": _key(),
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": 1,
            "page_count": page_count,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") not in ("000",):
        return []

    rows = []
    for item in data.get("list", []):
        # stkqy_irds: 주식수 증감 (양수=취득, 음수=처분)
        irds_str = item.get("stkqy_irds", "0").replace(",", "").replace("-", "") or "0"
        irds_raw = item.get("stkqy_irds", "0").replace(",", "") or "0"
        try:
            irds = int(irds_raw)
        except ValueError:
            irds = 0

        rows.append({
            "rcept_dt": item.get("rcept_dt", ""),          # 접수일자
            "reporter": item.get("reprer_nm", ""),           # 보고자명
            "report_type": item.get("rcept_type", ""),       # 보고구분
            "shares_change": irds,                           # 주식수 증감 (양=취득, 음=처분)
            "shares_total": _parse_int(item.get("stkqy", "0")),
            "ownership_pct": _parse_float(item.get("ctr_rate", "0")),
            "corp_name": item.get("corp_name", ""),
            "trade_type": "BUY" if irds > 0 else "SELL" if irds < 0 else "OTHER",
        })
    return rows


def _parse_int(s: str) -> int:
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0


def _parse_float(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0
