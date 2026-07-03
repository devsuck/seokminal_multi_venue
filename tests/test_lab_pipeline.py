"""AI LAB 파이프라인 합성 테스트.

검증: 합성 통과/REJECT, BLOCKED_BY_DATA, 매칭 random 무엣지≈50pct, 비용 스트레스,
snapshot 스키마, live 미실행 가드, 오토파일럿 큐 소진.
"""
from __future__ import annotations

import time

from research.lab import pipeline as pl
from research.lab.evaluator import evaluate, evaluate_synthetic
from research.lab.hypotheses import SEED_QUEUE, Hypothesis


def _h(**kw) -> Hypothesis:
    """evaluate_synthetic 직접 검증용(jarvis 배치 하네스 수학)."""
    base = dict(id="t", name="t", family="event", market="KR", thesis="", kill="",
                entry="", hold="", universe="", cost_bps=40.0, data_mode="synthetic_demo",
                n_trades=40, holding=[10], edge_bps=0.0, seed=1)
    base.update(kw)
    return Hypothesis(**base)


def _hb(hid: str) -> Hypothesis:
    """블록 가설 — 루프 플럼빙 테스트용(빠름·실데이터 무관, evaluate() 실경로)."""
    return Hypothesis(id=hid, name=hid, family="event", market="KR", thesis="", kill="k",
                      entry="", hold="", universe="", cost_bps=40.0, data_mode="blocked")


# ── evaluator ────────────────────────────────────────────────
def test_blocked_by_data():
    h = next(x for x in SEED_QUEUE if x.data_mode == "blocked")
    r = evaluate(h)
    assert r["status"] == "blocked_by_data"
    assert r["audit"]["ok"] is False
    assert r["backtest"] is None


def test_synthetic_edge_beats_random():
    r = evaluate_synthetic(_h(edge_bps=150.0, n_trades=45, seed=200))
    assert r["powered"] is True
    assert r["random"]["percentile"] >= 80  # 강한 엣지 → 고percentile


def test_no_edge_is_near_random_median():
    # edge=0 → 전략이 random 분포 중앙 근처(20~80pct), 엣지로 오판 안 함
    pcts = [evaluate_synthetic(_h(edge_bps=0.0, seed=s))["random"]["percentile"] for s in range(1, 21)]
    avg = sum(pcts) / len(pcts)
    assert 30 <= avg <= 70, f"무엣지 평균 percentile {avg} — 중앙이어야"


def test_negative_edge_rejects():
    r = evaluate_synthetic(_h(edge_bps=-60.0, n_trades=40, seed=101))
    assert r["status"] in ("reject_demo", "weak_demo")
    assert r["backtest"]["strategy_net"] < r["random"]["random_median"] + 200


def test_cost_stress_reduces_net():
    lo = evaluate_synthetic(_h(edge_bps=100.0, seed=5), cost_bps=10.0)["backtest"]["strategy_net"]
    hi = evaluate_synthetic(_h(edge_bps=100.0, seed=5), cost_bps=200.0)["backtest"]["strategy_net"]
    assert hi < lo


def test_underpowered_flag():
    r = evaluate_synthetic(_h(edge_bps=100.0, n_trades=10, seed=5))
    assert r["powered"] is False
    assert r["status"] == "underpowered_demo"


# ── pipeline ─────────────────────────────────────────────────
def _drain(engine, timeout=5.0):
    t0 = time.time()
    while engine.busy() and time.time() - t0 < timeout:
        time.sleep(0.01)


def _seed_fast(eng, hyps):
    """루프 플럼빙 테스트용 — 실 family(느림) 대신 빠른 blocked 큐 주입."""
    eng._by_id = {h.id: h for h in hyps}
    eng._queue = [h.id for h in hyps]


def test_pipeline_runs_and_records(monkeypatch):
    monkeypatch.setattr(pl.time, "sleep", lambda *a, **k: None)
    eng = pl.LabEngine()
    _seed_fast(eng, [_hb("plumb_rec")])
    before = eng.stats["processed"]
    eng.start(hid="plumb_rec")
    _drain(eng)
    snap = eng.snapshot()
    assert eng.stats["processed"] == before + 1
    assert any(v["id"] == "plumb_rec" for v in snap["verdicts"])
    assert snap["current"] is None  # 처리 후 초기화


def test_snapshot_schema():
    eng = pl.LabEngine()
    snap = eng.snapshot()
    for k in ("status", "stage", "progress", "busy", "autopilot", "live_guard",
              "current", "metrics", "stats", "log", "verdicts", "queue"):
        assert k in snap, f"snapshot 누락: {k}"


def test_live_guard_never_armed(monkeypatch):
    monkeypatch.setattr(pl.time, "sleep", lambda *a, **k: None)
    eng = pl.LabEngine()
    _seed_fast(eng, [_hb("plumb_guard")])
    eng.start(hid="plumb_guard")
    _drain(eng)
    assert eng.snapshot()["live_guard"] == "disarmed"  # 자동 live 무장 절대 없음


def test_autopilot_drains_queue(monkeypatch):
    monkeypatch.setattr(pl.time, "sleep", lambda *a, **k: None)
    eng = pl.LabEngine()
    _seed_fast(eng, [_hb(f"plumb_ap{i}") for i in range(3)])
    n = len(eng.snapshot()["queue"])
    eng.start(autopilot=True)
    _drain(eng, timeout=8.0)
    snap = eng.snapshot()
    assert snap["autopilot"] is False        # 소진 후 자동 정지
    assert eng.stats["processed"] >= n
