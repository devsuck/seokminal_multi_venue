"""OpenInsider.com 내부자 오픈마켓 매수 이벤트 스크레이퍼 (무료, 키 불필요).

STOCK Act Form 4 P-Purchase 이벤트를 파싱해 이벤트 스터디용 리스트 반환.
URL: http://openinsider.com/screener (공개 데이터)
캐시: data/openinsider/purchases.json (7일 TTL)
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta

import requests

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "openinsider")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_TIMEOUT = 30

_SCREENER_URL = (
    "http://openinsider.com/screener"
    "?s=&o=&pl=&ph=&ll=&lh="
    "&fd={days}&fdr=&td=0&tdr="
    "&fdlyl=&fdlyh=&daysago="
    "&xp=1"           # P-Purchase only
    "&vl=10&vh="      # 최소 $10k 거래 (노이즈 제거)
    "&ocl=&och=&sic1=-1&sicl=100&sich=9999"
    "&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh="
    "&v2l=&v2h=&oc2l=&oc2h="
    "&sortcol=1&cnt={cnt}&Action=1"   # 공시일 내림차순
)


def _parse_rows(html: str) -> list[dict]:
    rows = re.findall(r"<tr[^>]*background[^>]*>(.*?)</tr>", html, re.DOTALL)
    events = []
    for row in rows:
        ticker_m = re.search(r'href="\/([A-Z]{1,5})"', row)
        if not ticker_m:
            continue
        ticker = ticker_m.group(1)

        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) < 9:
            continue

        # 컬럼: 0=amend 1=filing_datetime 2=trade_date 3=ticker_raw 4=company
        #        5=insider 6=title 7=type 8=price 9=qty 10=owned 11=delta_own 12=value
        trade_type = cells[7] if len(cells) > 7 else ""
        if "P - Purchase" not in trade_type:
            continue

        filing_date = cells[1][:10] if cells[1] else ""
        trade_date = cells[2] if len(cells) > 2 else ""

        price_str = re.sub(r"[^0-9.]", "", cells[8]) if len(cells) > 8 else ""
        qty_str = re.sub(r"[^0-9]", "", cells[9]) if len(cells) > 9 else ""
        val_str = re.sub(r"[^0-9.]", "", cells[12]) if len(cells) > 12 else ""

        try:
            price = float(price_str) if price_str else None
        except ValueError:
            price = None
        try:
            qty = int(qty_str) if qty_str else None
        except ValueError:
            qty = None
        try:
            value = float(val_str) if val_str else None
        except ValueError:
            value = None

        events.append({
            "ticker": ticker,
            "disclosure_date": filing_date,
            "trade_date": trade_date,
            "insider": cells[5] if len(cells) > 5 else "",
            "title": cells[6] if len(cells) > 6 else "",
            "price": price,
            "qty": qty,
            "value_usd": value,
        })
    return events


def fetch_purchases(days: int = 1461, cnt: int = 5000) -> list[dict]:
    """지난 N일간 오픈마켓 매수 이벤트 목록 (최대 cnt건).
    days=1461 ≈ 4년.
    """
    os.makedirs(STORE_DIR, exist_ok=True)
    cache = os.path.join(STORE_DIR, f"purchases_{days}d.json")

    if os.path.exists(cache):
        if date.fromtimestamp(os.path.getmtime(cache)) >= date.today() - timedelta(days=7):
            with open(cache) as f:
                return json.load(f)

    url = _SCREENER_URL.format(days=days, cnt=cnt)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"OpenInsider fetch 실패: {e}")

    events = _parse_rows(r.text)

    with open(cache, "w") as f:
        json.dump(events, f)
    return events


def load_events(min_date: str = "2022-01-01") -> list[dict]:
    """캐시된 이벤트 로드 (min_date 이후)."""
    events = fetch_purchases()
    return [e for e in events if e.get("disclosure_date", "") >= min_date]
