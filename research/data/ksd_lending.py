"""KSD 대차잔고 데이터 연못 — 종목별 전 히스토리(2008~) parquet 저장.

원천: data.go.kr GetStocLendBorrInfoService_V2/getStItemLendAndBorrStatu_V2.
ISIN당 요청 1~2번(전 히스토리 페이지네이션)이라 이벤트 유니버스(~1400종목)면 1~2시간.
재개 지원: 이미 저장된 종목 스킵.

CLI: PYTHONPATH=. python3 research/data/ksd_lending.py [--codes-from-events buyback,treasury_disposal]
"""
from __future__ import annotations

import json
import os
import sys
import time

import pandas as pd

from ksd.client import KSDClient, isin_from_code

STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "kr_lending")
_PAGE = 5000


def _load_env():
    """KSDClient는 환경변수만 봄 — .env 폴백(krx_api._cfg 패턴)."""
    env = os.path.join(os.path.dirname(os.path.dirname(STORE)), ".env")
    if not os.path.exists(env):
        return
    for ln in open(env):
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.strip().split("=", 1)
            os.environ.setdefault(k, v.strip('"'))


def pull_history(client: KSDClient, code: str) -> pd.DataFrame:
    """종목 전체 대차 히스토리. basDt·lnbRmanStckCnt(잔고)·lnbCclStckCnt(체결)·lnbRdptStckCnt(상환)."""
    rows: list[dict] = []
    page = 1
    while True:
        got = client._get("borrow_status", {"isinCd": isin_from_code(code),
                                            "pageNo": str(page), "numOfRows": str(_PAGE)})
        rows.extend(got)
        if len(got) < _PAGE:
            break
        page += 1
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in ("lnbCclStckCnt", "lnbRmanStckCnt", "lnbRdptStckCnt"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["basDt", "lnbCclStckCnt", "lnbRmanStckCnt", "lnbRdptStckCnt"]].sort_values("basDt")


def store_path(code: str) -> str:
    return os.path.join(STORE, f"{code}.parquet")


def pull_universe(codes: list[str], pace_s: float = 0.3, log=print) -> dict:
    """유니버스 pull(재개 지원). 반환: {saved, skipped, empty, errors}."""
    os.makedirs(STORE, exist_ok=True)
    _load_env()
    client = KSDClient(throttle_s=pace_s)
    stat = {"saved": 0, "skipped": 0, "empty": 0, "errors": 0}
    for i, code in enumerate(sorted(codes)):
        p = store_path(code)
        if os.path.exists(p):
            stat["skipped"] += 1
            continue
        try:
            df = pull_history(client, code)
        except Exception as e:
            stat["errors"] += 1
            log(f"  {code} ERR {str(e)[:80]}")
            continue
        if df.empty:
            stat["empty"] += 1
            # 빈 종목도 마커 저장(재시도 방지)
            pd.DataFrame(columns=["basDt", "lnbCclStckCnt", "lnbRmanStckCnt", "lnbRdptStckCnt"]).to_parquet(p)
        else:
            df.to_parquet(p)
            stat["saved"] += 1
        if (i + 1) % 50 == 0:
            log(f"  {i + 1}/{len(codes)} saved={stat['saved']} empty={stat['empty']} err={stat['errors']}")
    return stat


def load_lending(code: str) -> dict[str, float]:
    """{YYYY-MM-DD: 대차잔고주식수}. 없으면 빈 dict."""
    p = store_path(code)
    if not os.path.exists(p):
        return {}
    df = pd.read_parquet(p)
    if df.empty:
        return {}
    out = {}
    for bd, v in zip(df["basDt"], df["lnbRmanStckCnt"]):
        bd = str(bd)
        out[f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}"] = float(v) if pd.notna(v) else 0.0
    return out


def balance_asof(lending: dict[str, float], date: str, max_lag_days: int = 10):
    """date(YYYY-MM-DD) '이전'(< date) 가장 최근 잔고. 사전등록 D−2 규율은 호출부가 date를 조정.

    max_lag_days 초과로 오래된 값이면 None(대차 데이터 공백 = 조건 결측 처리).
    """
    import datetime as dt
    d = dt.date.fromisoformat(date)
    for lag in range(1, max_lag_days + 1):
        k = (d - dt.timedelta(days=lag)).isoformat()
        if k in lending:
            return lending[k]
    return None


def event_universe_codes(families: list[str]) -> list[str]:
    base = os.path.join(os.path.dirname(STORE), "kr")
    codes: set[str] = set()
    for fam in families:
        p = os.path.join(base, f"events_{fam}.jsonl")
        if not os.path.exists(p):
            continue
        for ln in open(p):
            if ln.strip():
                c = json.loads(ln).get("stock_code", "")
                if c and len(c) == 6:
                    codes.add(c)
    return sorted(codes)


if __name__ == "__main__":
    fams = ["buyback", "treasury_disposal"]
    for a in sys.argv[1:]:
        if a.startswith("--codes-from-events"):
            fams = a.split("=", 1)[1].split(",") if "=" in a else fams
    codes = event_universe_codes(fams)
    print(f"universe {len(codes)} codes from {fams}")
    t0 = time.time()
    stat = pull_universe(codes)
    print(f"done {stat} in {round((time.time() - t0) / 60, 1)}min")
