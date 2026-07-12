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
