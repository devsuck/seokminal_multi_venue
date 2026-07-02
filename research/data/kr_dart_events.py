"""KR 공시 이벤트 로더 (OpenDART 주요사항보고). 공개·합법·타임스탬프 이벤트.

주요사항보고(pblntf_ty=B)에 자기주식취득(buyback)/유상증자(dilution)/CB 등 밀집.
list.json 페이지네이션 → report_nm 키워드 필터 → {stock_code, date, report_nm}.
lookahead 방지: 공시일(rcept_dt) 기준, 진입은 다음날.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time

import requests

DART = "https://opendart.fss.or.kr/api/list.json"
STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "kr")


def _key() -> str:
    k = os.environ.get("OPENDART_API_KEY", "")
    if not k:  # .env 폴백
        env = os.path.join(os.path.dirname(STORE_DIR), ".env")
        if os.path.exists(env):
            for ln in open(env):
                if ln.startswith("OPENDART_API_KEY="):
                    k = ln.split("=", 1)[1].strip().strip('"')
    return k


# 이벤트 정의(report_nm 키워드). exclude로 반대 신호 제거.
EVENT_DEFS = {
    "buyback": {"include": ["자기주식취득"], "exclude": ["처분"], "bias": "bullish"},
    "buyback_cancel": {"include": ["소각"], "exclude": [], "bias": "bullish"},
    "rights_issue": {"include": ["유상증자"], "exclude": [], "bias": "bearish"},
    "cb_issue": {"include": ["전환사채"], "exclude": [], "bias": "bearish"},
}


def _fetch_window(key: str, bgn: str, end: str, d: dict, out: list, seen: set, pace_s: float):
    """단일 ≤3개월 윈도우 전 페이지 순회."""
    page, total_pages = 1, None
    while True:
        try:
            r = requests.get(DART, params={"crtfc_key": key, "bgn_de": bgn, "end_de": end,
                                           "pblntf_ty": "B", "page_no": page, "page_count": 100},
                             timeout=20).json()
        except Exception:
            time.sleep(1.0); continue
        if r.get("status") == "013":  # 조회 데이터 없음
            return
        if r.get("status") != "000":
            return
        if total_pages is None:
            total_pages = int(r.get("total_page", 1) or 1)
        for it in r.get("list", []):
            nm = it.get("report_nm", "")
            sc = (it.get("stock_code") or "").strip()
            if not sc or not any(k in nm for k in d["include"]) or any(k in nm for k in d["exclude"]):
                continue
            rcept = it.get("rcept_dt", "")
            kid = (sc, rcept, nm[:20])
            if kid in seen:
                continue
            seen.add(kid)
            out.append({"stock_code": sc, "corp_name": it.get("corp_name", ""),
                        "date": f"{rcept[:4]}-{rcept[4:6]}-{rcept[6:8]}", "report_nm": nm, "event": d["_name"]})
        if page >= total_pages:
            return
        page += 1
        time.sleep(pace_s)


def pull_events(event: str, years: float = 2.0, pace_s: float = 0.15, window_days: int = 85) -> list[dict]:
    """OpenDART list.json은 최대 3개월 범위 → window_days 청크로 순회."""
    d = {**EVENT_DEFS[event], "_name": event}
    key = _key()
    if not key:
        raise ValueError("OPENDART_API_KEY 없음")
    out, seen = [], set()
    today = dt.date.today()
    start = today - dt.timedelta(days=int(years * 365))
    cur = start
    while cur < today:
        w_end = min(cur + dt.timedelta(days=window_days), today)
        _fetch_window(key, cur.strftime("%Y%m%d"), w_end.strftime("%Y%m%d"), d, out, seen, pace_s)
        cur = w_end + dt.timedelta(days=1)
        time.sleep(pace_s)
    return out


def save_events(event: str, rows: list[dict]) -> str:
    os.makedirs(STORE_DIR, exist_ok=True)
    p = os.path.join(STORE_DIR, f"events_{event}.jsonl")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def load_events(event: str) -> list[dict]:
    p = os.path.join(STORE_DIR, f"events_{event}.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(ln) for ln in open(p) if ln.strip()]
