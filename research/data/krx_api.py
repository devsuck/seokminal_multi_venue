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

# 미조정 corp action(액면분할/감자 등) 탐지 시그니처: 종가 전일비 극단 점프(2배↑ or 1/2↓)인데
# marcap 전일비는 정상 범위 → split-adjust 안 된 가격으로 간주해 역조정.
SPLIT_PRICE_JUMP = 2.0
SPLIT_MARCAP_STABLE = (0.7, 1.4)


def _cfg():
    key = os.environ.get("KRX_API_KEY", ""); base = os.environ.get("KRX_BASE_URL", "")
    if not key:  # .env 폴백 (프로젝트 루트 .env — data/.env 아님)
        env = os.path.join(os.path.dirname(os.path.dirname(STORE)), ".env")
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


def _adjust_splits(s: dict) -> None:
    """미조정 corp action 역조정 — s의 open/high/low/close를 in-place로 뒤에서부터 누적 스케일.
    marcap은 애초에 split 영향 안 받으므로(가격×발행주식수) 건드리지 않음 — 탐지 기준 그대로 유지.
    탐지는 원본 close 스냅샷으로만(raw_closes) — 이미 조정된 값과 비교하면 같은 split이
    보정마다 재탐지돼 factor가 연쇄로 계속 곱해짐(오버플로/언더플로 원인)."""
    closes, marcaps = s["close"], s["marcap"]
    raw_closes = list(closes)
    n = len(closes)
    factor = 1.0
    for i in range(n - 1, 0, -1):
        c0, c1 = raw_closes[i - 1], raw_closes[i]
        m0, m1 = marcaps[i - 1], marcaps[i]
        if c0 > 0 and c1 > 0 and m0 > 0 and m1 > 0:
            price_ratio = c1 / c0
            marcap_ratio = m1 / m0
            jumped = price_ratio >= SPLIT_PRICE_JUMP or price_ratio <= 1 / SPLIT_PRICE_JUMP
            marcap_ok = SPLIT_MARCAP_STABLE[0] <= marcap_ratio <= SPLIT_MARCAP_STABLE[1]
            if jumped and marcap_ok:
                factor *= price_ratio
        if factor != 1.0:
            for k in ("open", "high", "low", "close"):
                s[k][i - 1] *= factor


def build_series(market: str, min_bars: int = 60) -> dict:
    """날짜별 스냅샷 → {code: {name, dates[], open/high/low/close/tval[], marcap[], sect[]}}.
    survivorship-free: 각 종목은 실제 거래된 날짜에만 존재.
    미조정 corp action(액면분할/감자 등)은 _adjust_splits로 역조정된 가격을 반환 — marcap은
    원본 그대로(split 무관). 탐지 시그니처: SPLIT_PRICE_JUMP/SPLIT_MARCAP_STABLE.

    컬럼 단위(numpy) 추출 — 행 단위 iterrows()는 다년치 전종목 스냅샷(수백만 row)에서
    Series 박싱 오버헤드로 메모리/시간을 몇 배씩 잡아먹어(autoresearch 주간잡 OOM 원인 중
    하나) 벡터화함. 출력 스키마·값은 기존과 동일."""
    files = sorted(glob.glob(os.path.join(market_dir(market), "*.parquet")))
    series: dict = {}
    for f in files:
        df = pd.read_parquet(f)
        codes = df["ISU_CD"].astype(str).to_numpy()
        names = df["ISU_NM"].fillna("").astype(str).to_numpy() if "ISU_NM" in df else [""] * len(df)
        markets = df["MKT_NM"].fillna("").astype(str).to_numpy() if "MKT_NM" in df else [""] * len(df)
        sects = df["SECT_TP_NM"].fillna("").astype(str).to_numpy() if "SECT_TP_NM" in df else [""] * len(df)
        bas_dd = df["BAS_DD"].astype(str).to_numpy()
        opens = df["TDD_OPNPRC"].fillna(0).astype(float).to_numpy()
        highs = df["TDD_HGPRC"].fillna(0).astype(float).to_numpy()
        lows = df["TDD_LWPRC"].fillna(0).astype(float).to_numpy()
        closes = df["TDD_CLSPRC"].fillna(0).astype(float).to_numpy()
        tvals = df["ACC_TRDVAL"].fillna(0).astype(float).to_numpy()
        marcaps = df["MKTCAP"].fillna(0).astype(float).to_numpy()
        for i, code in enumerate(codes):
            s = series.setdefault(code, {"name": names[i], "market": markets[i],
                                         "dates": [], "open": [], "high": [], "low": [], "close": [],
                                         "tval": [], "marcap": [], "sect": []})
            bd = bas_dd[i]
            s["dates"].append(f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}")
            s["open"].append(opens[i]); s["high"].append(highs[i])
            s["low"].append(lows[i]); s["close"].append(closes[i])
            s["tval"].append(tvals[i]); s["marcap"].append(marcaps[i])
            s["sect"].append(sects[i])
    series = {c: s for c, s in series.items() if len(s["dates"]) >= min_bars}
    for s in series.values():
        _adjust_splits(s)
    return series
