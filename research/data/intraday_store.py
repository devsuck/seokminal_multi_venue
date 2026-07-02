"""인트라데이 봉 저장소 — 평범한 parquet (Nautilus 카탈로그와 분리).

경로: data/intraday/{SYMBOL}_{TF}.parquet
컬럼: ts_utc(int epoch sec, UTC), open, high, low, close, volume
재개가능: save는 기존과 병합 후 ts_utc 중복제거·정렬.
"""
from __future__ import annotations

import os

import pandas as pd

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "intraday")
COLUMNS = ["ts_utc", "open", "high", "low", "close", "volume"]

TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


def path_for(symbol: str, tf: str) -> str:
    safe = symbol.replace("/", "_")
    return os.path.join(STORE_DIR, f"{safe}_{tf}.parquet")


def load_df(symbol: str, tf: str) -> pd.DataFrame:
    """저장된 봉 DataFrame(없으면 빈 프레임). ts_utc 오름차순."""
    p = path_for(symbol, tf)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_parquet(p)
    return df.sort_values("ts_utc").reset_index(drop=True)


def latest_ts(symbol: str, tf: str) -> int | None:
    df = load_df(symbol, tf)
    return int(df["ts_utc"].iloc[-1]) if len(df) else None


def save_bars(symbol: str, tf: str, rows: list[dict]) -> int:
    """rows(dict list)를 기존과 병합·중복제거·정렬 후 저장. 반환: 총 봉 수."""
    os.makedirs(STORE_DIR, exist_ok=True)
    new = pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    existing = load_df(symbol, tf)
    frames = [f for f in (existing, new) if len(f)]
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if len(merged):
        merged = (
            merged.dropna(subset=["ts_utc"])
            .drop_duplicates(subset=["ts_utc"], keep="last")
            .sort_values("ts_utc")
            .reset_index(drop=True)
        )
        merged["ts_utc"] = merged["ts_utc"].astype("int64")
    merged.to_parquet(path_for(symbol, tf), index=False)
    return len(merged)


def quality_report(symbol: str, tf: str) -> dict:
    """데이터 품질 요약: 봉수·기간·중복·큰 갭 수(연속 세션 내 예상 간격 초과)."""
    df = load_df(symbol, tf)
    n = len(df)
    if n == 0:
        return {"symbol": symbol, "tf": tf, "bars": 0}
    ts = df["ts_utc"].astype("int64").tolist()
    dups = n - len(set(ts))
    step = TF_SECONDS.get(tf, 900)
    # 인접 봉 간격이 step의 1.5배~1일 미만이면 세션 내 갭(장마감 야간갭은 제외)
    intraday_gaps = sum(1 for a, b in zip(ts, ts[1:]) if step * 1.5 < (b - a) < 86400)
    return {
        "symbol": symbol,
        "tf": tf,
        "bars": n,
        "duplicates": dups,
        "intraday_gaps": intraday_gaps,
        "start_utc": int(ts[0]),
        "end_utc": int(ts[-1]),
        "start": pd.to_datetime(ts[0], unit="s", utc=True).isoformat(),
        "end": pd.to_datetime(ts[-1], unit="s", utc=True).isoformat(),
    }


def load_ohlc_lists(symbol: str, tf: str) -> dict:
    """검증 하네스용: {ts, open, high, low, close, volume} 리스트."""
    df = load_df(symbol, tf)
    return {
        "ts": df["ts_utc"].astype("int64").tolist(),
        "open": df["open"].astype(float).tolist(),
        "high": df["high"].astype(float).tolist(),
        "low": df["low"].astype(float).tolist(),
        "close": df["close"].astype(float).tolist(),
        "volume": df["volume"].astype(float).tolist(),
    }
