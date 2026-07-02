"""Funding 패널 저장소 — coin × funding_time (parquet). HL funding은 시간당.

경로: data/funding/{COIN}.parquet
컬럼: funding_time(int epoch sec, UTC), funding_rate(float), premium(float)
재개가능: save 병합·중복제거·정렬. 품질(중복·갭·상장일·커버리지) 리포트.

trading cost와 funding cashflow는 분리 — funding은 보유 중 수취/지급, 별도 저장."""
from __future__ import annotations

import os

import pandas as pd

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "funding")
COLUMNS = ["funding_time", "funding_rate", "premium"]
HOUR = 3600


def path_for(coin: str) -> str:
    return os.path.join(STORE_DIR, f"{coin.replace('/', '_')}.parquet")


def load_df(coin: str) -> pd.DataFrame:
    p = path_for(coin)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(p).sort_values("funding_time").reset_index(drop=True)


def latest_ts(coin: str) -> int | None:
    df = load_df(coin)
    return int(df["funding_time"].iloc[-1]) if len(df) else None


def save_funding(coin: str, rows: list[dict]) -> int:
    os.makedirs(STORE_DIR, exist_ok=True)
    new = pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    existing = load_df(coin)
    frames = [f for f in (existing, new) if len(f)]
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if len(merged):
        merged = (merged.dropna(subset=["funding_time"])
                  .drop_duplicates(subset=["funding_time"], keep="last")
                  .sort_values("funding_time").reset_index(drop=True))
        merged["funding_time"] = merged["funding_time"].astype("int64")
    merged.to_parquet(path_for(coin), index=False)
    return len(merged)


def quality_report(coin: str) -> dict:
    df = load_df(coin)
    n = len(df)
    if n == 0:
        return {"coin": coin, "records": 0}
    ts = df["funding_time"].astype("int64").tolist()
    dups = n - len(set(ts))
    # 시간당 예상 → 인접 간격이 1h 초과면 갭
    gaps = sum(1 for a, b in zip(ts, ts[1:]) if (b - a) > HOUR * 1.5)
    return {
        "coin": coin, "records": n, "duplicates": dups, "gaps_gt_1h": gaps,
        "listing_utc": int(ts[0]),
        "start": pd.to_datetime(ts[0], unit="s", utc=True).isoformat(),
        "end": pd.to_datetime(ts[-1], unit="s", utc=True).isoformat(),
        "coverage_days": round((ts[-1] - ts[0]) / 86400, 1),
    }


def load_series(coin: str) -> dict:
    """검증용: {time, funding_rate, premium} 리스트."""
    df = load_df(coin)
    return {
        "time": df["funding_time"].astype("int64").tolist(),
        "funding_rate": df["funding_rate"].astype(float).tolist(),
        "premium": df["premium"].astype(float).tolist(),
    }
