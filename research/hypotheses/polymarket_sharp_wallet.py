"""Polymarket 샤프월렛 컨버전스 가설 — 공식 리더보드 상위 지갑이 새 포지션을 잡을 때,
같은 트레일링 윈도우 안에 다른 샤프월렛이 몇 명 더 동시에(마켓 무관 — 크로스마켓)
움직였는지가 forward return과 상관 있는지 검증한다.
`research/run_polymarket_sharp_wallet_collect.py`가 쌓은 체결 원장
(research/data/polymarket_sharp_wallet/)을 읽어 컨버전스 카운트 -> 가격 시계열 ->
다중호라이즌 forward return 라벨링까지 조립한다.
`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md` §7 참고.
상수는 전부 설계 시점 고정값이며 결과를 본 뒤 바꾸지 않는다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

_DATA_DIR = Path("research/data/polymarket_sharp_wallet")

CONVERGENCE_WINDOW_S = 600.0
MAX_CONVERGENCE_BUCKET = 3
RESAMPLE_GRID_S = 5.0
HORIZONS_S = [30, 120, 300]


def load_sharp_wallet_trades(dates: list[str]) -> pd.DataFrame:
    """research/data/polymarket_sharp_wallet/{date}.jsonl 로드. ts 오름차순 정렬.
    notional_usd/is_sharp_wallet/wallet_rank/wallet_pnl은 수집기가 이미 계산해
    저장 — 재계산 안 함. 반환 컬럼: ts, condition_id, side, price, size,
    proxy_wallet, notional_usd, is_sharp_wallet, wallet_rank, wallet_pnl."""
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
                rows.append({
                    "ts": float(row["timestamp"]), "condition_id": row["conditionId"],
                    "side": row["side"], "price": float(row["price"]), "size": float(row["size"]),
                    "proxy_wallet": row.get("proxyWallet"),
                    "notional_usd": float(row["notional_usd"]),
                    "is_sharp_wallet": bool(row["is_sharp_wallet"]),
                    "wallet_rank": row.get("wallet_rank"), "wallet_pnl": row.get("wallet_pnl"),
                })
    df = pd.DataFrame(rows, columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl",
    ])
    return df.sort_values("ts").reset_index(drop=True)


def build_convergence_count(trades: pd.DataFrame) -> pd.DataFrame:
    """is_sharp_wallet=True인 행(anchor)만 대상. 각 anchor 시각 t에 대해 마켓
    무관하게 t-CONVERGENCE_WINDOW_S ~ t 구간에 체결이 있는 다른 anchor들의
    distinct proxy_wallet 수(자기 자신 포함)를 convergence_count로 기록.
    convergence_bucket = min(convergence_count, MAX_CONVERGENCE_BUCKET). 반환
    컬럼: ts, condition_id, side, direction, notional_usd, proxy_wallet,
    convergence_count, convergence_bucket. ts 오름차순."""
    empty = pd.DataFrame(columns=[
        "ts", "condition_id", "side", "direction", "notional_usd", "proxy_wallet",
        "convergence_count", "convergence_bucket",
    ])
    if trades.empty:
        return empty
    anchors = trades[trades["is_sharp_wallet"]].sort_values("ts").reset_index(drop=True)
    if anchors.empty:
        return empty
    ts_arr = anchors["ts"].to_numpy()
    wallets = anchors["proxy_wallet"].to_numpy()
    records = []
    for i in range(len(anchors)):
        t = ts_arr[i]
        window_start = t - CONVERGENCE_WINDOW_S
        mask = (ts_arr >= window_start) & (ts_arr <= t)
        count = len(set(wallets[mask]))
        row = anchors.iloc[i]
        direction = 1.0 if str(row["side"]).upper() == "BUY" else -1.0
        records.append({
            "ts": row["ts"], "condition_id": row["condition_id"], "side": row["side"],
            "direction": direction, "notional_usd": row["notional_usd"],
            "proxy_wallet": row["proxy_wallet"], "convergence_count": count,
            "convergence_bucket": min(count, MAX_CONVERGENCE_BUCKET),
        })
    return pd.DataFrame(records)


def build_price_series(trades: pd.DataFrame, condition_id: str) -> pd.Series:
    """해당 condition_id의 모든 행(anchor+context 구분 없이)을 RESAMPLE_GRID_S
    그리드로 ffill 리샘플. whale의 build_price_series와 동일 로직, 입력 필터만
    다름(family 대신 condition_id 단일 마켓). index=ts 그리드(등간격). 데이터
    없으면 빈 Series."""
    sub = trades[trades["condition_id"] == condition_id].sort_values("ts")
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
    anchors: pd.DataFrame,
    price_series_by_market: dict[str, pd.Series],
    horizons: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """anchor(build_convergence_count 결과, convergence_bucket 포함)마다 각 h in
    horizons에 대해 forward_return = (price[t+h]-price[t])/price[t] * direction
    (모멘텀 컨벤션). anchor ts는 해당 마켓 그리드의 가장 가까운 이전 포인트로
    스냅한다. t+h가 그리드에 없거나 NaN이면 그 행 제외."""
    records = []
    for _, row in anchors.iterrows():
        cid = row["condition_id"]
        price = price_series_by_market.get(cid)
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
        for h in horizons:
            exit_ts = t_grid + h
            if exit_ts not in price.index:
                continue
            exit_price = price.loc[exit_ts]
            if pd.isna(exit_price):
                continue
            forward_return = (exit_price - entry_price) / entry_price * row["direction"]
            records.append({
                "ts": t_grid, "condition_id": cid, "horizon_s": h,
                "entry_price": entry_price, "exit_price": exit_price,
                "direction": row["direction"], "forward_return": forward_return,
                "convergence_bucket": row["convergence_bucket"],
            })
    return pd.DataFrame(records, columns=[
        "ts", "condition_id", "horizon_s", "entry_price", "exit_price",
        "direction", "forward_return", "convergence_bucket",
    ])
