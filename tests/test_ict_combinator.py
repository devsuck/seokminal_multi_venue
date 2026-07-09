"""ICT 자유조합 백테스트 테스트 — 단일 프리미티브(killzone)로 진입 필터링·통계 산출 검증.

정확성 초점(FVG/sweep/OB/MS 판정은 test_ict_primitives.py에서 이미 검증됨). 여기선
combinator가 AND결합·eligible pool·underpowered short-circuit을 올바르게 하는지 본다.
"""
from __future__ import annotations

import datetime as dt

from research.ict.combinator import PRIMITIVE_IDS, evaluate_combo


def _bars(n: int = 400, kz_every: int = 4) -> dict:
    """15분봉 흉내. kz_every개 중 1개만 킬존(14:00 UTC) 시각으로 심는다."""
    ts, o, h, l, c = [], [], [], [], []
    base = dt.datetime(2024, 6, 3, 0, 0, tzinfo=dt.timezone.utc)
    px = 100.0
    for i in range(n):
        hour = 14 if i % kz_every == 0 else 20  # 킬존 vs 킬존 밖
        t = base.replace(hour=hour) + dt.timedelta(days=i // kz_every)
        ts.append(int(t.timestamp()))
        px += 0.01
        o.append(px); h.append(px + 0.5); l.append(px - 0.5); c.append(px + 0.1)
    return {"ts": ts, "o": o, "h": h, "l": l, "c": c}


def test_killzone_only_filters_to_time_window():
    bars = _bars(n=600, kz_every=4)
    res = evaluate_combo(bars, ["killzone"], direction="bullish", hold=2, n_runs=50)
    assert res["n_entries"] > 0
    # 진입 전부 킬존(14시) 시각이어야 함
    for i in res["entries_idx"]:
        assert dt.datetime.fromtimestamp(bars["ts"][i], tz=dt.timezone.utc).hour == 14


def test_underpowered_when_too_few_entries():
    bars = _bars(n=60, kz_every=4)  # 짧은 구간 → 진입 5개 미만
    res = evaluate_combo(bars, ["killzone", "fvg", "order_block", "sweep"], hold=2, n_runs=30)
    assert res["verdict"] == "UNDERPOWERED"
    assert res["net"] is None


def test_empty_primitives_returns_error():
    bars = _bars(n=100)
    res = evaluate_combo(bars, [], n_runs=10)
    assert "error" in res


def test_unknown_primitive_returns_error():
    bars = _bars(n=100)
    res = evaluate_combo(bars, ["not_a_real_primitive"], n_runs=10)
    assert "error" in res


def _zigzag_bars(n: int = 500) -> dict:
    """지그재그 파동(스윙·BOS·갭·연속캔들열 골고루 생기게) — ote/unicorn/ifvg/cisd/turtle_soup용."""
    ts, o, h, l, c = [], [], [], [], []
    base = dt.datetime(2024, 6, 3, 0, 0, tzinfo=dt.timezone.utc)
    px = 100.0
    for i in range(n):
        leg = (i // 7) % 2  # 7봉마다 상승/하락 레그 전환
        step = 0.8 if leg == 0 else -0.8
        px += step + (0.3 if i % 13 == 0 else 0.0)  # 가끔 변위(갭 유발)
        t = base + dt.timedelta(minutes=15 * i)
        ts.append(int(t.timestamp()))
        oo = px
        cc = px + step * 0.6
        o.append(oo); c.append(cc)
        h.append(max(oo, cc) + 0.4)
        l.append(min(oo, cc) - 0.4)
    return {"ts": ts, "o": o, "h": h, "l": l, "c": c}


def test_new_primitives_run_without_crashing():
    bars = _zigzag_bars(n=500)
    for p in ("ote", "unicorn", "ifvg", "cisd", "turtle_soup"):
        for d in ("bullish", "bearish"):
            res = evaluate_combo(bars, [p], direction=d, hold=2, n_runs=20)
            assert "n_entries" in res
            assert res["n_entries"] >= 0


def test_and_combo_of_new_primitives_is_subset():
    bars = _zigzag_bars(n=500)
    single = evaluate_combo(bars, ["cisd"], direction="bullish", hold=2, n_runs=20)
    combo = evaluate_combo(bars, ["cisd", "turtle_soup"], direction="bullish", hold=2, n_runs=20)
    assert combo["n_entries"] <= single["n_entries"]


def test_all_primitive_ids_are_dispatchable():
    bars = _zigzag_bars(n=500)
    for p in PRIMITIVE_IDS:
        res = evaluate_combo(bars, [p], direction="bullish", hold=2, n_runs=10)
        assert "error" not in res
