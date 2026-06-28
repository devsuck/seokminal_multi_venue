"""Korean stock universe from KIND (kind.krx.co.kr).

Downloads full KRX-listed stock list (KOSPI + KOSDAQ + KONEX) via
KIND's public HTML page, caches in memory for 24 hours.
No API key required.
"""
from __future__ import annotations

import io
import time

import pandas as pd
import requests

_KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
_CACHE_TTL_SECONDS = 86400  # 24 hours

_cache: list[dict] = []
_cache_ts: float = 0.0


def get_universe(
    session: requests.Session | None = None,
    kind_url: str = _KIND_URL,
) -> list[dict]:
    """Return full KRX stock list, refreshing from KIND if cache is stale.

    Each item: {"code": "005930", "name": "삼성전자", "market": "유가증권"}
    """
    global _cache, _cache_ts
    if _cache and time.time() - _cache_ts < _CACHE_TTL_SECONDS:
        return _cache

    active_session = session or requests.Session()
    r = active_session.get(
        kind_url,
        params={"method": "download", "searchType": 13},
        headers={"Referer": "https://kind.krx.co.kr/"},
        timeout=15,
    )
    r.raise_for_status()
    df = pd.read_html(io.StringIO(r.text), encoding="euc-kr")[0]
    df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
    _cache = [
        {
            "code": str(row["종목코드"]),
            "name": str(row["회사명"]),
            "market": str(row["시장구분"]),
        }
        for _, row in df.iterrows()
    ]
    _cache_ts = time.time()
    return _cache


def search_universe(q: str, max_results: int = 20) -> list[dict]:
    """Search cache by name or code (case-insensitive contains).

    Returns up to max_results matching items. Returns [] for empty query.
    """
    q_stripped = q.strip()
    if not q_stripped:
        return []
    universe = get_universe()
    q_lower = q_stripped.lower()
    matches = [
        item
        for item in universe
        if q_lower in item["name"].lower() or q_lower in item["code"]
    ]
    return matches[:max_results]
