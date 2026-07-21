"""지갑별 MLB 성적 집계 + 3지표 walk-forward 스페셜리스트 랭킹 — 순수함수.

각 MLB 체결을 "경기 정산까지 보유한 베팅"으로 취급(다각화 봇과 동일 단순화 —
중간 매도 무시). 베팅 손익 = (payout - price) * size, payout ∈ {1(승),0(패)}.
walk-forward: as_of 시점에 이미 *정산된* 마켓의 베팅만 성적에 반영(미래 결과로
스페셜리스트 뽑는 look-ahead 차단, 스펙 §3.3).
"""
from __future__ import annotations

import pandas as pd

_STAT_COLS = [
    "proxy_wallet", "mlb_pnl", "mlb_n", "mlb_winrate", "mlb_roi",
    "mlb_notional", "mlb_specialization",
]
_METRIC_COL = {"pnl": "mlb_pnl", "winrate": "mlb_winrate", "roi": "mlb_roi"}


def wallet_mlb_stats(
    trades: pd.DataFrame,
    resolutions: dict[str, dict],
    total_vol: dict[str, float] | None = None,
    as_of: float | None = None,
) -> pd.DataFrame:
    """MLB 체결(proxy_wallet, condition_id, side, price, size, notional_usd, ts) +
    정산결과 resolutions[cid] = {winning_side, resolved_ts}로 지갑별 성적 집계.
    total_vol[wallet] = 전체(전카테고리) 거래량 → 특화도. as_of 주면 그 시점까지
    정산된 마켓만. 반환: proxy_wallet, mlb_pnl, mlb_n, mlb_winrate, mlb_roi,
    mlb_notional, mlb_specialization."""
    if trades.empty:
        return pd.DataFrame(columns=_STAT_COLS)
    total_vol = total_vol or {}
    acc: dict[str, dict] = {}
    for _, row in trades.iterrows():
        res = resolutions.get(row["condition_id"])
        if res is None:
            continue  # 미정산 마켓 무시
        if as_of is not None and float(res.get("resolved_ts", float("inf"))) > as_of:
            continue  # walk-forward: as_of 이후 정산분 제외
        price = float(row["price"])
        size = float(row["size"])
        won = row["side"] == res["winning_side"]
        pnl = (1.0 if won else 0.0) - price
        pnl *= size
        a = acc.setdefault(row["proxy_wallet"], {"pnl": 0.0, "n": 0, "wins": 0, "notional": 0.0})
        a["pnl"] += pnl
        a["n"] += 1
        a["wins"] += 1 if won else 0
        a["notional"] += float(row["notional_usd"])

    rows = []
    for w, a in acc.items():
        if a["n"] == 0:
            continue
        tv = total_vol.get(w)
        spec = min(a["notional"] / tv, 1.0) if tv else 1.0
        rows.append({
            "proxy_wallet": w,
            "mlb_pnl": round(a["pnl"], 4),
            "mlb_n": a["n"],
            "mlb_winrate": a["wins"] / a["n"],
            "mlb_roi": (a["pnl"] / a["notional"]) if a["notional"] else 0.0,
            "mlb_notional": round(a["notional"], 4),
            "mlb_specialization": spec,
        })
    return pd.DataFrame(rows, columns=_STAT_COLS)


def rank_specialists(
    stats: pd.DataFrame,
    metric: str,
    n: int,
    min_bets: int,
    min_spec: float,
) -> list[str]:
    """게이트(mlb_n ≥ min_bets AND mlb_specialization ≥ min_spec) 통과한 지갑을
    metric("pnl"/"winrate"/"roi") 내림차순 상위 n명. 반환: proxy_wallet 리스트."""
    if stats.empty:
        return []
    col = _METRIC_COL[metric]
    gated = stats[(stats["mlb_n"] >= min_bets) & (stats["mlb_specialization"] >= min_spec)]
    return gated.sort_values(col, ascending=False)["proxy_wallet"].head(n).tolist()
