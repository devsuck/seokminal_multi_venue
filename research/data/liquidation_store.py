"""청산(liquidation) 이벤트 저장소 — coin별 parquet. Binance 선물 forceOrder 스트림 소스.

경로: data/liquidation/{COIN}.parquet
컬럼: ts(int epoch sec, UTC), side("long"/"short" — 청산된 포지션 방향), qty(float),
      price(float), venue(str)
자연키 없음(개별 체결 이벤트) — dedup은 (ts, side, qty, price, venue) 전체 조합 기준."""
from __future__ import annotations

import os

import pandas as pd

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "liquidation")
COLUMNS = ["ts", "side", "qty", "price", "venue"]
DEDUP_KEYS = ["ts", "side", "qty", "price", "venue"]


def path_for(coin: str) -> str:
    return os.path.join(STORE_DIR, f"{coin.replace('/', '_')}.parquet")


def load_df(coin: str) -> pd.DataFrame:
    p = path_for(coin)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(p).sort_values("ts").reset_index(drop=True)


def save_liquidations(coin: str, rows: list[dict]) -> int:
    os.makedirs(STORE_DIR, exist_ok=True)
    new = pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    existing = load_df(coin)
    frames = [f for f in (existing, new) if len(f)]
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if len(merged):
        merged = (merged.dropna(subset=["ts"])
                  .drop_duplicates(subset=DEDUP_KEYS, keep="last")
                  .sort_values("ts").reset_index(drop=True))
        merged["ts"] = merged["ts"].astype("int64")
    merged.to_parquet(path_for(coin), index=False)
    return len(merged)


def quality_report(coin: str) -> dict:
    df = load_df(coin)
    n = len(df)
    if n == 0:
        return {"coin": coin, "records": 0}
    ts = df["ts"].astype("int64").tolist()
    return {
        "coin": coin, "records": n,
        "long_count": int((df["side"] == "long").sum()),
        "short_count": int((df["side"] == "short").sum()),
        "start": pd.to_datetime(ts[0], unit="s", utc=True).isoformat(),
        "end": pd.to_datetime(ts[-1], unit="s", utc=True).isoformat(),
        "coverage_days": round((ts[-1] - ts[0]) / 86400, 1),
    }


def load_series(coin: str) -> dict:
    """검증용: {time, side, qty, price, venue} 리스트."""
    df = load_df(coin)
    return {
        "time": df["ts"].astype("int64").tolist(),
        "side": df["side"].astype(str).tolist(),
        "qty": df["qty"].astype(float).tolist(),
        "price": df["price"].astype(float).tolist(),
        "venue": df["venue"].astype(str).tolist(),
    }
