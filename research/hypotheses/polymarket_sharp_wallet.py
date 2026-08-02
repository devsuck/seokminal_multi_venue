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
    저장 — 재계산 안 함. outcome_index는 Data API의 outcomeIndex 원본값을 정규화
    없이 그대로 통과(0/1/999-비이진 센티널/None 가능). 반환 컬럼: ts, condition_id,
    side, price, size, proxy_wallet, notional_usd, is_sharp_wallet, wallet_rank,
    wallet_pnl, outcome_index."""
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
                    "outcome_index": row.get("outcomeIndex"),
                })
    df = pd.DataFrame(rows, columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl", "outcome_index",
    ])
    return df.sort_values("ts").reset_index(drop=True)


def build_convergence_count(trades: pd.DataFrame) -> pd.DataFrame:
    """is_sharp_wallet=True인 행(anchor)만 대상. 각 anchor 시각 t에 대해 마켓
    무관하게 t-CONVERGENCE_WINDOW_S ~ t 구간에 체결이 있는 다른 anchor들의
    distinct proxy_wallet 수(자기 자신 포함)를 convergence_count로 기록.
    convergence_bucket = min(convergence_count, MAX_CONVERGENCE_BUCKET). outcome_index는
    trades의 값을 그대로 pass-through(집행봇이 Yes/No 사이드 판정에 사용, 이 함수는
    해석 안 함). 반환 컬럼: ts, condition_id, side, direction, notional_usd,
    proxy_wallet, convergence_count, convergence_bucket, outcome_index. ts 오름차순."""
    empty = pd.DataFrame(columns=[
        "ts", "condition_id", "side", "direction", "notional_usd", "proxy_wallet",
        "convergence_count", "convergence_bucket", "outcome_index",
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
            "outcome_index": row["outcome_index"],
        })
    return pd.DataFrame(records)


def _percentile_rank_0_100(values: pd.Series) -> pd.Series:
    """값들을 [0,100] 구간 percentile로 변환 — 최솟값=0, 최댓값=100(동석 있으면
    average rank). n<2면 정의 불가 — 전부 NaN."""
    n = len(values)
    if n < 2:
        return pd.Series([float("nan")] * n, index=values.index)
    ranks = values.rank(method="average")
    return (ranks - 1) / (n - 1) * 100.0


def build_convergence_score(trades: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    """anchors(build_convergence_count 반환)에 4개 percentile 컴포넌트 평균인
    score 컬럼을 추가한다. 컴포넌트: wallet_count(convergence_count 재사용),
    pnl_sum(컨버전스 윈도우 내 distinct sharp wallet들의 wallet_pnl 합),
    notional(anchor 자체 notional_usd), liquidity(anchor.ts ~
    anchor.ts+max(HORIZONS_S) 구간 동일 condition_id의 모든 체결 notional_usd
    합). anchor 2건 미만이면 percentile 정의 불가 — score 전부 NaN. 반환 컬럼:
    입력 anchors 전체 + pnl_sum_raw, notional_raw, liquidity_raw, score."""
    out = anchors.copy()
    if out.empty:
        out["pnl_sum_raw"] = pd.Series(dtype=float)
        out["notional_raw"] = pd.Series(dtype=float)
        out["liquidity_raw"] = pd.Series(dtype=float)
        out["score"] = pd.Series(dtype=float)
        return out

    sharp = trades[trades["is_sharp_wallet"]]
    sharp_ts = sharp["ts"].to_numpy()
    sharp_wallets = sharp["proxy_wallet"].to_numpy()
    sharp_pnl = sharp["wallet_pnl"].to_numpy()
    liquidity_window_s = max(HORIZONS_S)

    pnl_sums = []
    liquidity_sums = []
    for _, row in out.iterrows():
        t = row["ts"]
        window_mask = (sharp_ts >= t - CONVERGENCE_WINDOW_S) & (sharp_ts <= t)
        seen: dict[str, float] = {}
        for w, p in zip(sharp_wallets[window_mask], sharp_pnl[window_mask]):
            seen[w] = p
        pnl_sums.append(sum(seen.values()))

        cid = row["condition_id"]
        liq_mask = ((trades["condition_id"] == cid) & (trades["ts"] >= t)
                    & (trades["ts"] <= t + liquidity_window_s))
        liquidity_sums.append(trades.loc[liq_mask, "notional_usd"].sum())

    out["pnl_sum_raw"] = pnl_sums
    out["notional_raw"] = out["notional_usd"].to_numpy()
    out["liquidity_raw"] = liquidity_sums

    if len(out) < 2:
        out["score"] = float("nan")
        return out

    wallet_count_pct = _percentile_rank_0_100(out["convergence_count"])
    pnl_sum_pct = _percentile_rank_0_100(out["pnl_sum_raw"])
    notional_pct = _percentile_rank_0_100(out["notional_raw"])
    liquidity_pct = _percentile_rank_0_100(out["liquidity_raw"])
    out["score"] = (wallet_count_pct.to_numpy() + pnl_sum_pct.to_numpy()
                     + notional_pct.to_numpy() + liquidity_pct.to_numpy()) / 4.0
    return out


def build_price_series(trades: pd.DataFrame, condition_id: str, outcome_index: int) -> pd.Series:
    """해당 condition_id의 행 중 outcome_index가 일치하는 것만(anchor+context
    구분 없이) RESAMPLE_GRID_S 그리드로 ffill 리샘플. 바이너리 마켓의 Yes/No는
    별개 토큰이라 가격이 서로 무관 — outcome 필터 없이 섞으면 두 토큰의
    가격이 하나의 시계열에 뒤섞인다. index=ts 그리드(등간격). 데이터 없으면
    빈 Series."""
    sub = trades[(trades["condition_id"] == condition_id)
                 & (trades["outcome_index"] == outcome_index)].sort_values("ts")
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
    price_series_by_market: dict[tuple[str, int], pd.Series],
    horizons: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """anchor(build_convergence_count 결과, convergence_bucket+outcome_index
    포함)마다 각 h in horizons에 대해 forward_return =
    (price[t+h]-price[t])/price[t] * direction(모멘텀 컨벤션). price는
    anchor의 (condition_id, outcome_index) 쌍으로 조회 — Yes/No는 별개 토큰이라
    같은 조회키 아니면 다른 토큰의 가격이 섞인다. outcome_index가 {0,1} 밖이면
    (비이진 센티널/결측) 어느 토큰인지 알 수 없어 그 anchor는 제외. anchor ts는
    해당 마켓 그리드의 가장 가까운 이전 포인트로 스냅한다. t+h가 그리드에
    없거나 NaN이면 그 행 제외. anchors에 score 컬럼이 있으면 그대로
    pass-through, 없으면 NaN."""
    has_score = "score" in anchors.columns
    records = []
    for _, row in anchors.iterrows():
        cid = row["condition_id"]
        outcome_index = row["outcome_index"]
        if outcome_index not in (0, 1):
            continue
        price = price_series_by_market.get((cid, outcome_index))
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
                "score": row["score"] if has_score else float("nan"),
            })
    return pd.DataFrame(records, columns=[
        "ts", "condition_id", "horizon_s", "entry_price", "exit_price",
        "direction", "forward_return", "convergence_bucket", "score",
    ])
