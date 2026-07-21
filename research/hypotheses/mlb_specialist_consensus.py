"""MLB 스페셜리스트 컨센서스 신호 + 라벨링 — 순수함수.

선정된 스페셜리스트들의 현재 포지션에서, 한 마켓에 충분히 몰리고(min_present)
같은 방향 합의(majority|unanimous)면 그 방향 신호. 라벨은 경기 정산까지 보유한
이진 결과(payout ∈ {1,0})로 forward return을 매긴다. 비용은 검증 러너에서 차감.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

_LABEL_COLS = ["condition_id", "side", "entry_price", "exit_price", "direction", "forward_return"]


def consensus_signals(
    positions: list[dict],
    specialists: list[str],
    min_present: int,
    threshold: str,
) -> list[dict]:
    """positions: [{proxy_wallet, condition_id, side}] — 스페셜리스트 현재 포지션 스냅샷.
    마켓별로 스페셜리스트 중 참여 수 ≥ min_present이고, threshold(majority=과반 |
    unanimous=전원) 조건 만족 시 최다 방향 신호. 반환: [{condition_id, side,
    n_present, n_agree}]."""
    spec = set(specialists)
    by_market: dict[str, list[str]] = {}
    for p in positions:
        if p["proxy_wallet"] in spec:
            by_market.setdefault(p["condition_id"], []).append(p["side"])

    signals = []
    for cid, sides in by_market.items():
        present = len(sides)
        if present < min_present:
            continue
        top_side, top_n = Counter(sides).most_common(1)[0]
        agree = (top_n == present) if threshold == "unanimous" else (top_n * 2 > present)
        if agree:
            signals.append({"condition_id": cid, "side": top_side,
                            "n_present": present, "n_agree": top_n})
    return signals


def build_labels(
    signals: list[dict],
    resolutions: dict[str, dict],
    entry_prices: dict[str, dict],
) -> pd.DataFrame:
    """신호마다 경기 정산까지 보유 라벨. entry_prices[cid][side] = 신호 시점 가격,
    payout = 1(승)/0(패). forward_return = (payout - entry)/entry * direction(=1, 롱).
    정산 안 됐거나 가격 없으면 제외. 반환 컬럼: condition_id, side, entry_price,
    exit_price(payout), direction, forward_return."""
    rows = []
    for s in signals:
        cid, side = s["condition_id"], s["side"]
        res = resolutions.get(cid)
        if res is None:
            continue
        ep = entry_prices.get(cid, {}).get(side)
        if ep is None or ep <= 0:
            continue
        payout = 1.0 if side == res["winning_side"] else 0.0
        rows.append({
            "condition_id": cid, "side": side, "entry_price": ep,
            "exit_price": payout, "direction": 1.0,
            "forward_return": (payout - ep) / ep,
        })
    return pd.DataFrame(rows, columns=_LABEL_COLS)
