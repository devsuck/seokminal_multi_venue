"""Polymarket whale 동시다발 동조 가설 — 단일 고래 팔로우(폐기, 3연속 no_edge) 대신
같은 마켓·같은 방향으로 서로 다른 지갑 여러 개가 짧은 시간창 안에 동조할 때만 신호로
채택한다. 단일 고래 체결은 도박/헤지 노이즈와 구분 안 되지만, 서로 무관한 지갑들의
독립적 동시 진입은 우연이거나(랜덤 베이스라인이 걸러줌) 공유된 정보 우위일 가능성이
`polymarket_whale`의 순수 사이즈 z-score보다 높다는 것이 이 가설의 핵심 재료.

`research.hypotheses.polymarket_whale`의 로드/z-score/스파이크/가격시계열/라벨링
빌더를 그대로 재사용 — 새로 만드는 건 스파이크→동조클러스터 필터 하나뿐.
"""
from __future__ import annotations

import pandas as pd

from research.hypotheses.polymarket_whale import (  # noqa: F401 (재수출 — 검증러너 편의)
    HORIZONS_S,
    RESAMPLE_GRID_S,
    WHALE_ZSCORE_THRESHOLD,
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)

COINCIDENCE_WINDOW_S = 60.0
MIN_WALLETS = 2

_COLS = ["ts", "condition_id", "family", "direction", "outcome_index",
         "proxy_wallet", "notional_usd", "notional_z", "n_wallets", "member_wallets"]


def build_coincidence_signal(
    spikes: pd.DataFrame,
    window_s: float = COINCIDENCE_WINDOW_S,
    min_wallets: int = MIN_WALLETS,
) -> pd.DataFrame:
    """`build_spike_signal`이 뽑은 개별 고래체결 중, 같은 (condition_id, direction)
    안에서 window_s초 내 서로 다른 proxy_wallet이 min_wallets개 이상 나타나는
    클러스터만 남긴다. 신호 확정 시점 = 그 조건을 채운 마지막 체결의 ts(그 전엔
    "동조"인지 알 수 없다 — look-ahead 없음). 클러스터당 신호 1개, 확정 즉시 다음
    앵커로 건너뛰어 오버랩 중복을 막는다. 반환 컬럼은 `build_labels_multi_horizon`이
    요구하는 ts/condition_id/family/direction/outcome_index/proxy_wallet 그대로 유지해
    라벨링 함수를 무수정 재사용할 수 있게 한다.
    ponytail: 그룹당 O(n) 투포인터, 클러스터 내부 순서는 무시(집합 크기만 봄) — 지갑
    3개 이상 동조 시 우선순위 가중치 같은 건 아직 없음, 필요해지면 추가."""
    if spikes.empty:
        return pd.DataFrame(columns=_COLS)
    out = []
    for (cid, direction), g in spikes.groupby(["condition_id", "direction"], sort=False):
        g = g.sort_values("ts").reset_index(drop=True)
        n = len(g)
        start = 0
        while start < n:
            t_anchor = g["ts"].iloc[start]
            wallets_seen: dict[str, None] = {}
            confirmed_at = None
            j = start
            while j < n and g["ts"].iloc[j] - t_anchor <= window_s:
                w = g["proxy_wallet"].iloc[j]
                if w is not None:
                    wallets_seen[w] = None
                if len(wallets_seen) >= min_wallets:
                    confirmed_at = j
                    break
                j += 1
            if confirmed_at is not None:
                row = g.iloc[confirmed_at]
                out.append({
                    "ts": row["ts"], "condition_id": cid, "family": row["family"],
                    "direction": direction, "outcome_index": row["outcome_index"],
                    "proxy_wallet": row["proxy_wallet"],
                    "notional_usd": row["notional_usd"], "notional_z": row["notional_z"],
                    "n_wallets": len(wallets_seen), "member_wallets": sorted(wallets_seen.keys()),
                })
                start = confirmed_at + 1
            else:
                start += 1
    return pd.DataFrame(out, columns=_COLS)
