"""ICT 프리미티브 자유조합 백테스트 — research/ict/strategy.py(model_a 고정조합)를 일반화.

ICT 실전은 킬존·sweep·FVG·OB·BOS/CHoCH·OTE·unicorn·iFVG·CISD·turtle soup을 단독이 아니라
여러 개 동시에 AND결합해서 씀 — 이 모듈은 그 임의 부분집합 조합을 전부 지원.

주의: killzone+sweep+FVG(model A) / silver bullet / OTE / unicorn / iFVG / CISD / SMT
표준조합은 이미 BH-FDR+레드팀 정식 파이프라인에서 REJECT 확정
(research/agents/experiment_registry.jsonl, hypothesis_id 접두 'ict_'/'ict2024_').
여기서 만드는 임의조합은 그 결론을 뒤집는 증거가 아니라 **탐색용 플레이그라운드** —
매칭random 대비 p-value/percentile은 참고치, 정식 후보 등록 아님.
"""
from __future__ import annotations

from research.ict.primitives import (
    cisd_events,
    fair_value_gaps,
    ifvg_events,
    killzone_indices,
    liquidity_sweeps,
    market_structure,
    order_blocks,
    ote_touches,
    turtle_soup_events,
    unicorn_zones,
)
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.engine import simulate_fixed_hold_longs

PRIMITIVE_IDS = (
    "fvg", "order_block", "sweep", "killzone", "market_structure",
    "ote", "unicorn", "ifvg", "cisd", "turtle_soup",
)


def _evt_indices(events: list[dict], direction: str) -> set[int]:
    return {e["idx"] for e in events if e["type"] == direction}


def _fvg_indices(h: list[float], l: list[float], direction: str, window: int = 1) -> set[int]:
    fvgs = fair_value_gaps(h, l)
    idxs = {f["idx"] for f in fvgs if f["type"] == direction}
    out: set[int] = set()
    for i in range(len(h)):
        if any(j in idxs for j in range(max(0, i - window), i + 1)):
            out.add(i)
    return out


def _order_block_indices(o, h, l, c, direction: str) -> set[int]:
    obs = order_blocks(o, h, l, c)
    return {ob["idx"] + 1 for ob in obs if ob["type"] == direction}  # 변위봉(i+1)에서 유효


def _sweep_indices(h, l, c, direction: str, lookback: int) -> set[int]:
    sw = liquidity_sweeps(h, l, c, lookback=lookback)
    return {s["idx"] for s in sw if s["type"] == direction}


def _ms_indices(h, l, c, direction: str, k: int) -> set[int]:
    ev = market_structure(h, l, c, k=k)
    return {e["idx"] for e in ev if e["dir"] == direction}


def _stats_vs_random(
    closes: list[float],
    entries: list[int],
    hold: int,
    cost_bps: float,
    trade_size: float,
    eligible: list[int],
    n_runs: int,
    seed: int,
) -> dict:
    """entries 확정 후 공통 꼬리부: 진입<5개면 UNDERPOWERED, 아니면 매칭random 대비 통계."""
    if len(entries) < 5:
        return {"n_entries": len(entries), "verdict": "UNDERPOWERED", "net": None,
                "percentile": None, "p": None}

    trades = simulate_fixed_hold_longs(closes, entries, [hold] * len(entries), trade_size, cost_bps)
    strat_net = sum(t["pnl"] for t in trades)

    rand = random_same_frequency(closes, n_trades=len(entries), holding_periods=[hold],
                                  trade_size=trade_size, cost_bps=cost_bps,
                                  eligible_indices=eligible, n_runs=n_runs, seed=seed)
    ev = empirical_p_value(strat_net, rand)

    mid = len(entries) // 2
    wf1 = sum(t["pnl"] for t in simulate_fixed_hold_longs(
        closes, entries[:mid], [hold] * mid, trade_size, cost_bps)) if mid else 0.0
    wf2 = sum(t["pnl"] for t in simulate_fixed_hold_longs(
        closes, entries[mid:], [hold] * (len(entries) - mid), trade_size, cost_bps)) if len(entries) - mid else 0.0

    return {
        "n_entries": len(entries), "n_eligible": len(eligible),
        "net": round(strat_net, 4), "percentile": ev["percentile"], "p": ev["p_value"],
        "rand_median": ev["random_median"],
        "wf_first": round(wf1, 4), "wf_second": round(wf2, 4),
        "entries_idx": entries[:200],  # 차트 마커용 상한
    }


def evaluate_combo(
    bars: dict,
    primitives: list[str],
    direction: str = "bullish",
    hold: int = 8,
    cost_bps: float = 5.0,
    trade_size: float = 1.0,
    lookback: int = 10,
    swing_k: int = 2,
    kz: tuple[float, float] = (13.5, 15.0),
    window: int = 8,
    near: int = 3,
    min_run: int = 2,
    confirm: int = 3,
    n_runs: int = 500,
    seed: int = 42,
) -> dict:
    """primitives: PRIMITIVE_IDS 부분집합, 전부 AND로 결합(고전 ICT식 다중확증).
    direction: bullish|bearish. killzone은 방향 무관 시간필터.
    반환: entries/eligible n + 매칭random 대비 net/percentile/p(+wf1/wf2) — 참고치."""
    if not primitives:
        return {"error": "프리미티브 최소 1개 선택"}

    o, h, l, c, ts = bars["o"], bars["h"], bars["l"], bars["c"], bars["ts"]
    n = len(c)

    sets: list[set[int]] = []
    for p in primitives:
        if p == "fvg":
            sets.append(_fvg_indices(h, l, direction))
        elif p == "order_block":
            sets.append(_order_block_indices(o, h, l, c, direction))
        elif p == "sweep":
            sets.append(_sweep_indices(h, l, c, direction, lookback))
        elif p == "killzone":
            sets.append(set(killzone_indices(ts, kz[0], kz[1])))
        elif p == "market_structure":
            sets.append(_ms_indices(h, l, c, direction, swing_k))
        elif p == "ote":
            sets.append(_evt_indices(ote_touches(h, l, c, swing_k, window), direction))
        elif p == "unicorn":
            sets.append(_evt_indices(unicorn_zones(o, h, l, c, near), direction))
        elif p == "ifvg":
            sets.append(_evt_indices(ifvg_events(h, l, c, window), direction))
        elif p == "cisd":
            sets.append(_evt_indices(cisd_events(o, h, l, c, min_run), direction))
        elif p == "turtle_soup":
            sets.append(_evt_indices(turtle_soup_events(h, l, c, swing_k, confirm), direction))
        else:
            return {"error": f"미지원 프리미티브: {p}"}

    combo = set(range(n))
    for s in sets:
        combo &= s
    entries = sorted(i for i in combo if i + hold < n and i + 1 < n)

    # eligible = killzone 선택 시 그 시간창, 아니면 전 구간(랜덤 baseline 모집단)
    if "killzone" in primitives:
        eligible = sorted(i for i in killzone_indices(ts, kz[0], kz[1]) if i + hold < n)
    else:
        eligible = list(range(n - hold - 1))

    closes_dir = c if direction == "bullish" else [-x for x in c]
    return _stats_vs_random(closes_dir, entries, hold, cost_bps, trade_size, eligible, n_runs, seed)


# ── 차트 시각화용 원본 이벤트/존 (AND결합 전, 프리미티브별 개별 노출) ──
POINT_PRIMITIVES = {"sweep", "market_structure", "ote", "ifvg", "cisd", "turtle_soup"}
ZONE_PRIMITIVES = {"fvg", "order_block", "unicorn"}
BAND_PRIMITIVES = {"killzone"}


def _runs(idxs: list[int]) -> list[tuple[int, int]]:
    """정렬된 인덱스를 연속구간 (start,end) 리스트로 묶음."""
    if not idxs:
        return []
    idxs = sorted(idxs)
    out = [[idxs[0], idxs[0]]]
    for i in idxs[1:]:
        if i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [(a, b) for a, b in out]


def detect_events(
    bars: dict,
    primitives: list[str],
    direction: str = "bullish",
    lookback: int = 10,
    swing_k: int = 2,
    kz: tuple[float, float] = (13.5, 15.0),
    window: int = 8,
    near: int = 3,
    min_run: int = 2,
    confirm: int = 3,
    zone_extend: int = 20,
) -> dict[str, list[dict]]:
    """차트 오버레이용: 각 프리미티브의 원본 이벤트/존을 개별 노출(AND결합 안 함, 참고용).
    point: {idx, type}. zone/band: {idx, idx_end, type?, lo?, hi?}."""
    o, h, l, c, ts = bars["o"], bars["h"], bars["l"], bars["c"], bars["ts"]
    n = len(c)
    out: dict[str, list[dict]] = {}

    for p in primitives:
        if p == "fvg":
            fvgs = [f for f in fair_value_gaps(h, l) if f["type"] == direction]
            out[p] = [
                {"idx": max(0, f["idx"] - 2), "idx_end": min(n - 1, f["idx"] + zone_extend),
                 "type": f["type"], "lo": f["gap_lo"], "hi": f["gap_hi"]}
                for f in fvgs
            ]
        elif p == "order_block":
            obs = [ob for ob in order_blocks(o, h, l, c) if ob["type"] == direction]
            out[p] = [
                {"idx": ob["idx"], "idx_end": min(n - 1, ob["idx"] + zone_extend),
                 "type": ob["type"], "lo": ob["zone_lo"], "hi": ob["zone_hi"]}
                for ob in obs
            ]
        elif p == "unicorn":
            fvgs = fair_value_gaps(h, l)
            fvg_by_key = {(f["idx"], f["type"]): f for f in fvgs}
            uz = [u for u in unicorn_zones(o, h, l, c, near) if u["type"] == direction]
            zones = []
            for u in uz:
                f = fvg_by_key.get((u["idx"], u["type"]))
                if f is None:
                    continue
                zones.append({"idx": max(0, f["idx"] - 2), "idx_end": min(n - 1, f["idx"] + zone_extend),
                              "type": u["type"], "lo": f["gap_lo"], "hi": f["gap_hi"]})
            out[p] = zones
        elif p == "killzone":
            idxs = killzone_indices(ts, kz[0], kz[1])
            out[p] = [{"idx": a, "idx_end": b} for a, b in _runs(idxs)]
        elif p == "sweep":
            out[p] = [{"idx": e["idx"], "type": e["type"]}
                      for e in liquidity_sweeps(h, l, c, lookback=lookback) if e["type"] == direction]
        elif p == "market_structure":
            out[p] = [{"idx": e["idx"], "type": e["dir"]}
                      for e in market_structure(h, l, c, k=swing_k) if e["dir"] == direction]
        elif p == "ote":
            out[p] = [{"idx": e["idx"], "type": e["type"]}
                      for e in ote_touches(h, l, c, swing_k, window) if e["type"] == direction]
        elif p == "ifvg":
            out[p] = [{"idx": e["idx"], "type": e["type"]}
                      for e in ifvg_events(h, l, c, window) if e["type"] == direction]
        elif p == "cisd":
            out[p] = [{"idx": e["idx"], "type": e["type"]}
                      for e in cisd_events(o, h, l, c, min_run) if e["type"] == direction]
        elif p == "turtle_soup":
            out[p] = [{"idx": e["idx"], "type": e["type"]}
                      for e in turtle_soup_events(h, l, c, swing_k, confirm) if e["type"] == direction]

    return out
