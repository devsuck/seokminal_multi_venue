"""크로스벤뉴(HL/Binance/OKX) 오더북 임밸런스 괴리(스큐) 가설.

`research/run_cross_venue_skew_collect.py`가 쌓은 벤뉴별 raw 스냅샷을 읽어
임밸런스 계산 -> 공통 그리드 정렬 -> 벤뉴간 괴리 -> 스파이크 탐지 -> 다중호라이즌
forward return 라벨링까지 조립한다. 상수는 전부 설계 시점 고정값이며 결과를 본
뒤 바꾸지 않는다(`docs/superpowers/specs/2026-07-12-cross-venue-skew-design.md`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_DATA_DIR = Path("research/data/cross_venue_skew")

IMBALANCE_DEPTH_N = 5  # OKX books5가 top5까지만 주므로 3개 벤뉴 공통 depth.
                        # 최적화 대상 아님, 결과 보고 안 바꿈.
RESAMPLE_GRID_S = 1.0
FFILL_TOLERANCE_S = 5.0
DIVERGENCE_ZSCORE_LOOKBACK = 300
SPIKE_ZSCORE_THRESHOLD = 2.0
HORIZONS_S = [5, 15, 60]


def load_venue_snapshots(venue: str, coin: str, dates: list[str]) -> pd.DataFrame:
    """research/data/cross_venue_skew/{venue}_{coin}_{date}.jsonl 로드.
    반환 컬럼: ts(float), bids(list[dict]), asks(list[dict]). ts 오름차순 정렬."""
    rows = []
    for date in dates:
        path = _DATA_DIR / f"{venue}_{coin}_{date}.jsonl"
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows.append({"ts": row["ts"], "bids": row["bids"], "asks": row["asks"]})
    df = pd.DataFrame(rows, columns=["ts", "bids", "asks"])
    return df.sort_values("ts").reset_index(drop=True)


def build_imbalance(df: pd.DataFrame, depth_n: int = IMBALANCE_DEPTH_N) -> pd.Series:
    """시점별 imbalance = sum(bid.size[:depth_n]) / (sum(bid.size[:depth_n]) + sum(ask.size[:depth_n])).
    0.5=중립, 1에 가까울수록 매수우위. 양쪽 합이 0이면 0.5. index=ts."""
    def _imb(row):
        bid_sum = sum(lvl["size"] for lvl in row["bids"][:depth_n])
        ask_sum = sum(lvl["size"] for lvl in row["asks"][:depth_n])
        total = bid_sum + ask_sum
        return bid_sum / total if total > 0 else 0.5

    values = df.apply(_imb, axis=1)
    return pd.Series(values.values, index=df["ts"].values)


def align_venues(imbalance_by_venue: dict[str, pd.Series]) -> pd.DataFrame:
    """RESAMPLE_GRID_S 그리드로 각 벤뉴 시계열을 asof-backward-fill
    (tolerance=FFILL_TOLERANCE_S) 정렬. 컬럼=벤뉴명. tolerance 초과분은 NaN으로
    남기고(추정값으로 메우지 않음), 이후 계산에서 자연스럽게 제외된다."""
    if not imbalance_by_venue:
        return pd.DataFrame()

    non_empty = {v: s for v, s in imbalance_by_venue.items() if len(s)}
    if not non_empty:
        return pd.DataFrame(columns=list(imbalance_by_venue))

    min_ts = min(s.index.min() for s in non_empty.values())
    max_ts = max(s.index.max() for s in non_empty.values())
    n_steps = int((max_ts - min_ts) // RESAMPLE_GRID_S) + 1
    grid = [min_ts + i * RESAMPLE_GRID_S for i in range(n_steps)]

    out = pd.DataFrame(index=grid)
    for venue, series in imbalance_by_venue.items():
        s = series.sort_index()
        left = pd.DataFrame({"ts": grid})
        right = pd.DataFrame({"ts": s.index.values, "value": s.values}).sort_values("ts")
        merged = pd.merge_asof(left, right, on="ts", direction="backward", tolerance=FFILL_TOLERANCE_S)
        out[venue] = merged["value"].values
    out.index.name = "ts"
    return out


def build_price_series(raw_books_by_venue: dict[str, pd.DataFrame]) -> pd.Series:
    """RESAMPLE_GRID_S 그리드에서 벤뉴별 mid=(best_bid+best_ask)/2를 구하고
    벤뉴간 평균 — 레이블 계산용 단일 가격 시계열(코인당 1개).
    best_bid/best_ask는 리스트 순서를 신뢰하지 않고 명시적으로
    best_bid=max(bid.price), best_ask=min(ask.price)로 계산한다."""
    if not raw_books_by_venue:
        return pd.Series(dtype=float)

    def _mid(row):
        if not row["bids"] or not row["asks"]:
            return float("nan")
        best_bid = max(lvl["price"] for lvl in row["bids"])
        best_ask = min(lvl["price"] for lvl in row["asks"])
        return (best_bid + best_ask) / 2.0

    mids_by_venue: dict[str, pd.Series] = {}
    for venue, df in raw_books_by_venue.items():
        values = df.apply(_mid, axis=1)
        mids_by_venue[venue] = pd.Series(values.values, index=df["ts"].values)

    aligned = align_venues(mids_by_venue)
    return aligned.mean(axis=1, skipna=True)


def build_skew_divergence(aligned: pd.DataFrame) -> pd.DataFrame:
    """벤뉴 컬럼 2개 이상 유효한 시점만 대상. 각 벤뉴 v에 대해
    divergence[v] = imbalance[v] - mean(imbalance[다른 벤뉴들])."""
    venues = list(aligned.columns)
    out = pd.DataFrame(index=aligned.index)
    valid_count = aligned.notna().sum(axis=1)
    for v in venues:
        others = [c for c in venues if c != v]
        others_mean = aligned[others].mean(axis=1, skipna=True) if others else pd.Series(float("nan"), index=aligned.index)
        div = aligned[v] - others_mean
        out[v] = div.where(valid_count >= 2)
    return out


def build_spike_signal(
    divergence: pd.DataFrame,
    lookback: int = DIVERGENCE_ZSCORE_LOOKBACK,
    threshold: float = SPIKE_ZSCORE_THRESHOLD,
) -> pd.DataFrame:
    """벤뉴별 divergence 컬럼마다 롤링(lookback) z-score 계산, |z|>=threshold인
    시점을 스파이크로 표시. long-format 반환(컬럼: ts, venue, spike, direction) —
    build_labels_multi_horizon이 이벤트 단위로 순회하기 위함."""
    records = []
    for venue in divergence.columns:
        series = divergence[venue]
        roll_mean = series.rolling(window=lookback, min_periods=lookback).mean()
        roll_std = series.rolling(window=lookback, min_periods=lookback).std()
        z = (series - roll_mean) / roll_std
        spike = (z.abs() >= threshold) & roll_std.gt(0)
        for ts, is_spike, div_val in zip(divergence.index, spike.values, series.values):
            if is_spike:
                records.append({
                    "ts": ts, "venue": venue, "spike": True,
                    "direction": 1.0 if div_val > 0 else -1.0,
                })
    return pd.DataFrame(records, columns=["ts", "venue", "spike", "direction"])


def build_labels_multi_horizon(
    price: pd.Series,
    spikes: pd.DataFrame,
    horizons_s: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """스파이크 시점 t마다 각 h in horizons_s에 대해
    forward_return = (price[t+h] - price[t]) / price[t] * direction(모멘텀 컨벤션).
    t+h가 price 인덱스에 없거나(범위 밖) NaN이면 그 행 제외. price/spikes 모두
    align_venues가 만든 동일 1s그리드 위에 있으므로 t+h는 정확히 그리드 포인트에
    떨어진다(horizons_s가 전부 RESAMPLE_GRID_S의 배수)."""
    price = price.sort_index()
    records = []
    for _, row in spikes.iterrows():
        t, venue, direction = row["ts"], row["venue"], row["direction"]
        if t not in price.index or pd.isna(price.loc[t]):
            continue
        entry_price = price.loc[t]
        for h in horizons_s:
            exit_ts = t + h
            if exit_ts not in price.index:
                continue
            exit_price = price.loc[exit_ts]
            if pd.isna(exit_price):
                continue
            forward_return = (exit_price - entry_price) / entry_price * direction
            records.append({
                "ts": t, "venue": venue, "horizon_s": h,
                "entry_price": entry_price, "exit_price": exit_price,
                "direction": direction, "forward_return": forward_return,
            })
    return pd.DataFrame(records, columns=[
        "ts", "venue", "horizon_s", "entry_price", "exit_price", "direction", "forward_return",
    ])
