"""Polymarket whale tracking 가설 — 큰 체결 이후 가격이 그 방향으로 선행 이동하는지.

`research/run_polymarket_whale_collect.py`가 쌓은 체결 원장(research/data/polymarket_whale/)을
읽어 마켓별 notional z-score -> 스파이크(고래) 탐지 -> 가격 시계열 -> 다중호라이즌
forward return 라벨링까지 조립한다. 상수는 전부 설계 시점 고정값이며 결과를 본 뒤
바꾸지 않는다(`docs/superpowers/specs/2026-07-13-polymarket-whale-tracking-design.md`).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

_DATA_DIR = Path("research/data/polymarket_whale")

NOTIONAL_ZSCORE_LOOKBACK = 100  # 트레이드 개수 기준(시간 기준 아님) — 마켓별 체결빈도 편차 커서.
NOTIONAL_ZSCORE_WARMUP = 20     # 이 미만 샘플이면 z-score 미계산(NaN).
WHALE_ZSCORE_THRESHOLD = 2.0
RESAMPLE_GRID_S = 5.0           # 수집기 폴링주기(5s)와 동일 — 이보다 촘촘한 그리드는 의미 없음.
HORIZONS_S = [30, 120, 300]


def load_whale_trades(dates: list[str]) -> pd.DataFrame:
    """research/data/polymarket_whale/{date}.jsonl 로드. notional_usd=price*size
    컬럼 추가. outcome_index는 Data API의 outcomeIndex 원본값을 정규화 없이 그대로
    통과(0/1/999-비이진 센티널/None 가능). 반환 컬럼: ts, condition_id, side, price,
    size, notional_usd, family, proxy_wallet(lowercase, 원본 API 응답에 이미 있던
    필드 — 지갑 역추적용), outcome_index. ts 오름차순 정렬."""
    rows = []
    for date in dates:
        path = _DATA_DIR / f"{date}.jsonl"
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                price = float(row["price"])
                size = float(row["size"])
                wallet = row.get("proxyWallet")
                rows.append({
                    "ts": float(row["timestamp"]), "condition_id": row["conditionId"],
                    "side": row["side"], "price": price, "size": size,
                    "notional_usd": price * size, "family": row.get("family"),
                    "proxy_wallet": wallet.lower() if wallet else None,
                    "outcome_index": row.get("outcomeIndex"),
                })
    df = pd.DataFrame(rows, columns=[
        "ts", "condition_id", "side", "price", "size", "notional_usd", "family", "proxy_wallet",
        "outcome_index",
    ])
    return df.sort_values("ts").reset_index(drop=True)


def build_notional_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """condition_id별로 그룹핑해 notional_usd의 롤링(NOTIONAL_ZSCORE_LOOKBACK, 트레이드
    개수 기준) z-score를 계산한다. 그룹 내 표본이 NOTIONAL_ZSCORE_WARMUP 미만이거나
    표준편차 0이면 z=NaN. 반환: 입력 컬럼 + notional_z, ts 오름차순."""
    if df.empty:
        return df.assign(notional_z=pd.Series(dtype=float))
    out_parts = []
    for _cid, g in df.groupby("condition_id", sort=False):
        g = g.sort_values("ts").copy()
        roll_mean = g["notional_usd"].rolling(
            window=NOTIONAL_ZSCORE_LOOKBACK, min_periods=NOTIONAL_ZSCORE_WARMUP).mean()
        roll_std = g["notional_usd"].rolling(
            window=NOTIONAL_ZSCORE_LOOKBACK, min_periods=NOTIONAL_ZSCORE_WARMUP).std()
        z = (g["notional_usd"] - roll_mean) / roll_std
        g["notional_z"] = z.where(roll_std.gt(0))
        out_parts.append(g)
    return pd.concat(out_parts).sort_values("ts").reset_index(drop=True)


def build_spike_signal(df_with_z: pd.DataFrame, threshold: float = WHALE_ZSCORE_THRESHOLD) -> pd.DataFrame:
    """|notional_z| >= threshold인 행만 남긴다(고래 체결). direction: side가 BUY면
    +1.0(가격 상승 방향), 그 외(SELL)면 -1.0. outcome_index는 그대로 pass-through.
    반환 컬럼: ts, condition_id, family, side, direction, notional_usd, notional_z,
    proxy_wallet, outcome_index."""
    mask = df_with_z["notional_z"].abs() >= threshold
    spikes = df_with_z[mask.fillna(False)].copy()
    spikes["direction"] = spikes["side"].apply(lambda s: 1.0 if str(s).upper() == "BUY" else -1.0)
    if "proxy_wallet" not in spikes.columns:
        spikes["proxy_wallet"] = None
    return spikes[[
        "ts", "condition_id", "family", "side", "direction", "notional_usd", "notional_z",
        "proxy_wallet", "outcome_index",
    ]].reset_index(drop=True)


def build_price_series(df: pd.DataFrame, condition_id: str, outcome_index: int) -> pd.Series:
    """해당 condition_id의 행 중 outcome_index가 일치하는 것만 RESAMPLE_GRID_S
    그리드로 ffill 리샘플. 바이너리 마켓의 Yes/No는 별개 토큰이라 가격이 서로
    무관 — outcome 필터 없이 섞으면 두 토큰의 가격이 하나의 시계열에 뒤섞인다.
    index=ts 그리드(등간격). 데이터 없으면 빈 Series."""
    sub = df[(df["condition_id"] == condition_id)
             & (df["outcome_index"] == outcome_index)].sort_values("ts")
    if sub.empty:
        return pd.Series(dtype=float)
    min_ts, max_ts = sub["ts"].iloc[0], sub["ts"].iloc[-1]
    n_steps = math.ceil((max_ts - min_ts) / RESAMPLE_GRID_S) + 1
    grid = [min_ts + i * RESAMPLE_GRID_S for i in range(n_steps)]
    left = pd.DataFrame({"ts": grid})
    right = sub[["ts", "price"]].rename(columns={"price": "value"})
    merged = pd.merge_asof(left, right, on="ts", direction="backward")
    return pd.Series(merged["value"].values, index=grid)


def build_labels_multi_horizon(
    price_by_condition: dict[tuple[str, int], pd.Series],
    spikes: pd.DataFrame,
    horizons_s: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """스파이크마다 각 h in horizons_s에 대해 forward_return =
    (price[t+h]-price[t])/price[t] * direction(모멘텀 컨벤션). price는 스파이크의
    (condition_id, outcome_index) 쌍으로 조회 — Yes/No는 별개 토큰이라 같은
    조회키 아니면 다른 토큰의 가격이 섞인다. outcome_index가 {0,1} 밖이면(비이진
    센티널/결측) 어느 토큰인지 알 수 없어 그 스파이크는 제외. 스파이크 ts는 해당
    마켓 그리드의 가장 가까운 이전 포인트로 스냅한다. t+h가 그리드에 없거나(범위 밖)
    NaN이면 그 행 제외. horizons_s는 RESAMPLE_GRID_S의 배수라 정확히 그리드에
    떨어진다(align_venues 방식과 동일 보장)."""
    records = []
    for _, row in spikes.iterrows():
        cid = row["condition_id"]
        outcome_index = row["outcome_index"]
        if outcome_index not in (0, 1):
            continue
        price = price_by_condition.get((cid, outcome_index))
        if price is None or price.empty:
            continue
        t = row["ts"]
        grid_before = [g for g in price.index if g <= t]
        if not grid_before:
            continue
        t_grid = grid_before[-1]
        entry_price = price.loc[t_grid]
        if pd.isna(entry_price):
            continue
        for h in horizons_s:
            exit_ts = t_grid + h
            if exit_ts not in price.index:
                continue
            exit_price = price.loc[exit_ts]
            if pd.isna(exit_price):
                continue
            forward_return = (exit_price - entry_price) / entry_price * row["direction"]
            records.append({
                "ts": t_grid, "condition_id": cid, "family": row["family"], "horizon_s": h,
                "entry_price": entry_price, "exit_price": exit_price,
                "direction": row["direction"], "forward_return": forward_return,
                "proxy_wallet": row.get("proxy_wallet"),
            })
    return pd.DataFrame(records, columns=[
        "ts", "condition_id", "family", "horizon_s", "entry_price", "exit_price",
        "direction", "forward_return", "proxy_wallet",
    ])
