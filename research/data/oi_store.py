"""OI(Open Interest) 패널 저장소 — coin × ts (parquet). HL metaAndAssetCtxs 스냅샷.

경로: data/oi/{COIN}.parquet
컬럼: ts(int epoch sec, UTC), open_interest(float), mark_px(float)
재개가능: save 병합·중복제거·정렬. 품질(중복·갭·커버리지) 리포트.

HL은 OI 히스토리 백필 API가 없다 — funding과 달리 지금부터 폴링 누적만 가능
(`research/run_oi_collect.py`를 주기적으로 돌려야 시계열이 쌓임)."""
from __future__ import annotations

import os

import pandas as pd

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "oi")
COLUMNS = ["ts", "open_interest", "mark_px"]
HOUR = 3600


def path_for(coin: str) -> str:
    return os.path.join(STORE_DIR, f"{coin.replace('/', '_')}.parquet")


def load_df(coin: str) -> pd.DataFrame:
    p = path_for(coin)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(p).sort_values("ts").reset_index(drop=True)


def latest_ts(coin: str) -> int | None:
    df = load_df(coin)
    return int(df["ts"].iloc[-1]) if len(df) else None


def save_oi(coin: str, rows: list[dict]) -> int:
    os.makedirs(STORE_DIR, exist_ok=True)
    new = pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    existing = load_df(coin)
    frames = [f for f in (existing, new) if len(f)]
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if len(merged):
        merged = (merged.dropna(subset=["ts"])
                  .drop_duplicates(subset=["ts"], keep="last")
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
    dups = n - len(set(ts))
    gaps = sum(1 for a, b in zip(ts, ts[1:]) if (b - a) > HOUR * 1.5)
    return {
        "coin": coin, "records": n, "duplicates": dups, "gaps_gt_1h": gaps,
        "start": pd.to_datetime(ts[0], unit="s", utc=True).isoformat(),
        "end": pd.to_datetime(ts[-1], unit="s", utc=True).isoformat(),
        "coverage_days": round((ts[-1] - ts[0]) / 86400, 1),
    }


def load_series(coin: str) -> dict:
    """검증용: {time, open_interest, mark_px} 리스트."""
    df = load_df(coin)
    return {
        "time": df["ts"].astype("int64").tolist(),
        "open_interest": df["open_interest"].astype(float).tolist(),
        "mark_px": df["mark_px"].astype(float).tolist(),
    }
