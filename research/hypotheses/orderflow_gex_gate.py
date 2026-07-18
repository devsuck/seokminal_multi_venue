"""가설: 오더플로우 confluence(footprint/absorption/cvd 2/3 다수결) x GEX 레짐 게이트.

기존 orderflow_context_gate.py의 build_confluence_signals를 그대로 재사용(신규 방향
로직 없음) — 여기서 새로 하는 일은 그 방향신호를 GEX 레짐(딜러 net gamma 부호)으로
분류만 한다. 어느 레짐이 "맞을지" 사전 가정 없음 — negative/positive 두 팔로 쪼개서
둘 다 랜덤 대비 검정(BH-FDR로 같이 보정), 데이터가 고르는 구조. 롱/숏 모두 그대로
살아있음(confluence 자체가 BUY/SELL 대칭 산출, 레짐 게이트는 방향을 바꾸지 않고
거래 자격만 필터링).

DORMANT 확인용 모듈. GEX 스냅샷 수집이 2026-07-17부터 시작이라 초반엔 대부분 구간이
STALE(레짐 판정 불가)로 나옴 — 수집 기간 누적돼야 표본 커짐.
"""
from __future__ import annotations

import bisect

from research.hypotheses.orderflow_context_gate import build_confluence_signals
from research.hypotheses.orderflow_futures import _footprint_buckets

# 고정값 — 결과 보고 바꾸지 않는다(데이터 스누핑 방지).
MAX_STALENESS_SEC = 300.0  # GEX_POLL_INTERVAL_SEC(60s)의 5배 — 폴링 실패 몇 번은 허용, 그 이상은 STALE


def aggregate_net_gex(snapshot: dict) -> float:
    """스트라이크별 net_gex 합산 — 만기 통합 전체 딜러 감마 포지셔닝 근사."""
    return sum(lv["net_gex"] for lv in snapshot.get("levels", []))


def nearest_gex_snapshot(
    gex_snapshots: list[dict], ts: float, max_staleness_sec: float = MAX_STALENESS_SEC
) -> dict | None:
    """ts 이전(<=) 가장 최근 스냅샷. max_staleness_sec 넘게 오래됐으면 None(STALE).
    gex_snapshots는 updated_at 오름차순 정렬 가정."""
    times = [s["updated_at"] for s in gex_snapshots]
    idx = bisect.bisect_right(times, ts) - 1
    if idx < 0:
        return None
    snap = gex_snapshots[idx]
    if ts - snap["updated_at"] > max_staleness_sec:
        return None
    return snap


def build_gex_regime_series(
    gex_snapshots: list[dict], bucket_ts: list[float], max_staleness_sec: float = MAX_STALENESS_SEC
) -> list[str | None]:
    """버킷별 레짐 라벨: "negative"(딜러 숏감마, 추세증폭 기대) / "positive"(딜러 롱감마,
    평균회귀 기대) / None(STALE, 판정 불가). 기대 방향은 가정일 뿐 필터링에 안 씀 —
    두 레짐 다 별도 팔로 실측."""
    regimes: list[str | None] = []
    for ts in bucket_ts:
        snap = nearest_gex_snapshot(gex_snapshots, ts, max_staleness_sec)
        if snap is None:
            regimes.append(None)
            continue
        net = aggregate_net_gex(snap)
        regimes.append("negative" if net < 0 else "positive")
    return regimes


def build_gex_gated_signals(deltas: list[dict], gex_snapshots: list[dict]) -> dict:
    """confluence 방향신호 + 레짐 라벨 동시 산출. eligible = confluence 판정 가능 &&
    레짐 STALE 아님(둘 다 갖춰진 구간만). signals는 confluence 그대로(레짐이 방향을
    안 바꿈, 자격만 봄) — 분석 시점에 regime_by_idx로 negative/positive 나눠서 각각
    검정."""
    conf = build_confluence_signals(deltas)
    order, *_ = _footprint_buckets(deltas)
    regime = build_gex_regime_series(gex_snapshots, order)

    eligible = [i for i in conf["eligible"] if regime[i] is not None]
    return {
        "closes": conf["closes"],
        "signals": conf["signals"],
        "eligible": eligible,
        "regime_by_idx": regime,
    }
