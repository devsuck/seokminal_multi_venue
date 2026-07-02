"""KRX 공식 OpenAPI (data-dbg.krx.co.kr) — 날짜별 전종목 스냅샷.

전 기간 스냅샷 = PIT universe + survivorship-free 자동(폐지종목은 활동기간에만 등장).
실 거래대금(ACC_TRDVAL)·시총(MKTCAP)·부서(관리종목 판별) 포함(프록시 아님).
날짜별 parquet 저장 → build_series로 종목별 시계열 재구성.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import time

import pandas as pd
import requests

STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "krx")
ENDPOINTS = {"KOSPI": "/svc/apis/sto/stk_bydd_trd", "KOSDAQ": "/svc/apis/sto/ksq_bydd_trd"}
NUM = ["TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS"]


def _cfg():
    key = os.environ.get("KRX_API_KEY", ""); base = os.environ.get("KRX_BASE_URL", "")
    if not key:  # .env 폴백
        env = os.path.join(os.path.dirname(STORE), ".env")
        if os.path.exists(env):
            for ln in open(env):
                if ln.startswith("KRX_API_KEY="):
                    key = ln.split("=", 1)[1].strip().strip('"')
                if ln.startswith("KRX_BASE_URL="):
                    base = ln.split("=", 1)[1].strip().strip('"')
    return key, base


def pull_snapshot(market: str, date: str, key: str, base: str) -> pd.DataFrame:
    """date=YYYYMMDD. 휴장/미래일이면 빈 DF."""
    r = requests.get(base + ENDPOINTS[market], headers={"AUTH_KEY": key},
                     params={"basDd": date}, timeout=20)
    rows = r.json().get("OutBlock_1", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in NUM:
        if c in df:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    return df


def market_dir(market: str) -> str:
    return os.path.join(STORE, market.lower())


def pull_range(market: str, start: str, end: str, pace_s: float = 0.25, log=print):
    """start~end 영업일 스냅샷 저장(날짜별 parquet). 재개: 이미 있는 날짜 스킵."""
    key, base = _cfg()
    if not key:
        raise ValueError("KRX_API_KEY 없음")
    os.makedirs(market_dir(market), exist_ok=True)
    d0 = dt.date.fromisoformat(start); d1 = dt.date.fromisoformat(end)
    cur = d0; saved = 0; empty = 0
    while cur <= d1:
        if cur.weekday() < 5:  # 평일만
            ds = cur.strftime("%Y%m%d")
            p = os.path.join(market_dir(market), f"{ds}.parquet")
            if not os.path.exists(p):
                try:
                    df = pull_snapshot(market, ds, key, base)
                    if len(df):
                        df.to_parquet(p); saved += 1
                    else:
                        empty += 1  # 휴장
                except Exception as e:
                    log(f"  {ds} ERR {str(e)[:50]}")
                time.sleep(pace_s)
                if saved % 50 == 0 and saved:
                    log(f"  {ds}: {saved} 거래일 저장")
        cur += dt.timedelta(days=1)
    log(f"완료: {saved} 거래일 저장, {empty} 휴장 스킵")
    return saved


def build_series(market: str, min_bars: int = 60) -> dict:
    """날짜별 스냅샷 → {code: {name, dates[], open/high/low/close/tval[], marcap[], sect[]}}.
    survivorship-free: 각 종목은 실제 거래된 날짜에만 존재."""
    files = sorted(glob.glob(os.path.join(market_dir(market), "*.parquet")))
    series: dict = {}
    for f in files:
        df = pd.read_parquet(f)
        for _, r in df.iterrows():
            code = str(r["ISU_CD"])
            s = series.setdefault(code, {"name": str(r.get("ISU_NM", "")), "market": str(r.get("MKT_NM", "")),
                                         "dates": [], "open": [], "high": [], "low": [], "close": [],
                                         "tval": [], "marcap": [], "sect": []})
            bd = str(r["BAS_DD"])
            s["dates"].append(f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}")
            s["open"].append(float(r["TDD_OPNPRC"] or 0)); s["high"].append(float(r["TDD_HGPRC"] or 0))
            s["low"].append(float(r["TDD_LWPRC"] or 0)); s["close"].append(float(r["TDD_CLSPRC"] or 0))
            s["tval"].append(float(r["ACC_TRDVAL"] or 0)); s["marcap"].append(float(r["MKTCAP"] or 0))
            s["sect"].append(str(r.get("SECT_TP_NM", "")))
    return {c: s for c, s in series.items() if len(s["dates"]) >= min_bars}
