"""US Congress insider trade history cache (FMP API).

공시일(disclosure_date) 기준 이벤트. 매수(BUY)만 추출.
data/congress/ 에 parquet 캐시. 최근 N페이지 풀링.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "congress")
_BASE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 12


def _key() -> str:
    k = os.environ.get("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
    if not k:
        env = os.path.join(os.path.dirname(os.path.dirname(STORE_DIR)), ".env")
        if os.path.exists(env):
            for ln in open(env):
                if ln.startswith("FINANCIAL_MODELING_PREP_API_KEY="):
                    k = ln.split("=", 1)[1].strip().strip('"')
    if not k:
        raise ValueError("FINANCIAL_MODELING_PREP_API_KEY not set")
    return k


def _norm(row: dict, chamber: str) -> dict:
    t = str(row.get("type", "")).lower()
    trade_type = "BUY" if "purchase" in t else "SELL" if "sale" in t or "sold" in t else "OTHER"
    return {
        "chamber": chamber,
        "trade_date": row.get("transactionDate", ""),
        "disclosure_date": row.get("disclosureDate", ""),
        "reporter": f"{row.get('firstName','')} {row.get('lastName','')}".strip(),
        "ticker": (row.get("symbol") or "").upper().strip(),
        "trade_type": trade_type,
        "amount_str": row.get("amount", ""),
    }


def _fetch_chamber(chamber: str, path: str, key: str, pages: int = 5) -> list[dict]:
    import requests
    rows: list[dict] = []
    for page in range(1, pages + 1):
        try:
            r = requests.get(f"{_BASE}/{path}", params={"apikey": key, "page": page}, timeout=_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            rows.extend(_norm(x, chamber) for x in data)
            time.sleep(0.2)
        except Exception:
            break
    return rows


def pull_history(pages: int = 10) -> list[dict]:
    """상·하원 BUY 이벤트 풀링. ticker 없는 것 제외."""
    key = _key()
    rows: list[dict] = []
    for chamber, path in (("senate", "senate-trading"), ("house", "house-trading")):
        rows.extend(_fetch_chamber(chamber, path, key, pages))
    # BUY only, ticker 필수
    rows = [r for r in rows if r["trade_type"] == "BUY" and r["ticker"] and r["disclosure_date"]]
    rows.sort(key=lambda x: x["disclosure_date"], reverse=True)
    return rows


def load_events(min_date: str = "2020-01-01") -> list[dict]:
    """캐시된 Congress BUY 이벤트 로드. 캐시 없으면 pull."""
    import json
    cache = os.path.join(STORE_DIR, "congress_events.json")
    os.makedirs(STORE_DIR, exist_ok=True)

    # 캐시 유효: 오늘 생성된 것
    if os.path.exists(cache):
        mtime = date.fromtimestamp(os.path.getmtime(cache))
        if mtime >= date.today() - timedelta(days=1):
            with open(cache) as f:
                events = json.load(f)
            return [e for e in events if e.get("disclosure_date", "") >= min_date]

    events = pull_history(pages=20)
    with open(cache, "w") as f:
        json.dump(events, f)
    return [e for e in events if e.get("disclosure_date", "") >= min_date]
