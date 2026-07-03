"""이벤트 레벨 OOS 검정 — 월 코호트(3개)보다 빨리 쌓이는 검정력(월 ~70건).

사전등록: p_worse = P(OOS 분포가 in-sample보다 나쁨), Mann-Whitney 단측.
arm 게이트(월 기준, 동결)는 불변 — 이건 보조 증거.
"""
from __future__ import annotations

import research.paper.buyback_forward as bf
from research.paper import buyback_edge as be


def _fake_generate(in_rets, oos_rets, frozen="2026-07-02"):
    """generate(write=False) 대체 — rows에 (date, ret). in=동결 전, oos=동결 후."""
    rows = [(f"2026-01-{i%28+1:02d}", r) for i, r in enumerate(in_rets)]
    rows += [(f"2026-08-{i%28+1:02d}", r) for i, r in enumerate(oos_rets)]
    return {"envelope": {"n_months": 20, "cohort_median_p10": -0.03,
                         "cohort_median_p90": 0.037, "cohort_median_avg": 0.0},
            "forward_cohorts": {}, "rows": rows}


def _patch(monkeypatch, in_rets, oos_rets):
    monkeypatch.setattr(bf, "generate", lambda since=None, write=True: _fake_generate(in_rets, oos_rets))
    be._cache.update(ts=0.0, data=None)  # 캐시 무효화


def test_event_level_block_present(monkeypatch):
    _patch(monkeypatch, in_rets=[0.01] * 50 + [-0.01] * 50, oos_rets=[0.005] * 30)
    r = be.edge_status(force=True)
    ev = r["event_level"]
    assert ev["n_oos"] == 30 and ev["n_in_sample"] == 100
    assert ev["powered"] is True  # n_oos >= 20


def test_oos_shifted_down_gives_small_p_worse(monkeypatch):
    # OOS가 명확히 나쁨(-3%) vs in-sample(+1%) → p_worse 작아야(엣지 소멸 신호)
    _patch(monkeypatch, in_rets=[0.01 + 0.001 * (i % 7) for i in range(100)],
           oos_rets=[-0.03 + 0.001 * (i % 5) for i in range(40)])
    ev = be.edge_status(force=True)["event_level"]
    assert ev["p_worse"] < 0.01


def test_oos_same_distribution_large_p(monkeypatch):
    rets = [(-1) ** i * 0.01 * (1 + i % 5) for i in range(120)]
    _patch(monkeypatch, in_rets=rets[:80], oos_rets=rets[80:])
    ev = be.edge_status(force=True)["event_level"]
    assert ev["p_worse"] > 0.05  # 같은 분포 → 소멸 신호 없음


def test_underpowered_below_20_events(monkeypatch):
    _patch(monkeypatch, in_rets=[0.01] * 100, oos_rets=[-0.05] * 5)
    ev = be.edge_status(force=True)["event_level"]
    assert ev["powered"] is False  # 5건으로 판단 금지(정직)


def test_month_gate_unchanged(monkeypatch):
    # 이벤트 레벨은 보조 — status(월 기준 동결 게이트)는 forward_cohorts 없으면 no_oos_yet 그대로
    _patch(monkeypatch, in_rets=[0.01] * 100, oos_rets=[0.01] * 30)
    r = be.edge_status(force=True)
    assert r["status"] == "no_oos_yet"
