from unittest.mock import patch

import pandas as pd

import research.run_polymarket_whale_validate as val


def test_run_family_blocked_when_no_data_for_family():
    df = pd.DataFrame(columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family"])
    result = val.run_family("news", df)
    assert result["blocked"] is True
    assert result["family"] == "news"


def test_run_family_blocked_when_below_min_events():
    rows = [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
              "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(5)]
    df = pd.DataFrame(rows)
    result = val.run_family("news", df)
    assert result["blocked"] is True


def test_main_handles_no_data_dir_without_crash(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        val.main()  # 예외 없이 끝나야 함(전 family BLOCKED 출력)


def _whale_trades_min():
    return pd.DataFrame([
        {"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5, "size": 100.0,
         "notional_usd": 5000.0, "family": "news"} for i in range(3)
    ])


def test_compute_report_no_data_returns_no_data_verdict():
    df = pd.DataFrame(columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family"])
    rep = val.compute_report(df, [])
    assert rep["hypothesis"] == "polymarket_whale"
    assert rep["verdict"] == "no_data"
    assert rep["pools"] == []
    assert rep["groups"] == []


def test_compute_report_single_whale_pool():
    rep = val.compute_report(_whale_trades_min(), ["2026-07-21"])
    assert [p["name"] for p in rep["pools"]] == ["whale"]
    for p in rep["pools"]:
        assert set(p) >= {"name", "alpha", "n_tested", "n_survivors", "survivors", "threshold"}
    assert rep["verdict"] in ("no_edge", "candidate")
    assert all("group" in g for g in rep["groups"])


def test_load_and_report_no_data(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        rep = val.load_and_report()
    assert rep["verdict"] == "no_data"


def test_walk_forward_both_positive():
    precomputed = [(1.0, 0.5, 0.6, 0.0), (1.0, 0.5, 0.6, 0.0),
                   (1.0, 0.5, 0.6, 0.0), (1.0, 0.5, 0.6, 0.0)]
    wf = val._walk_forward(precomputed)
    assert wf["both_positive"] is True
    assert wf["n_first"] == 2 and wf["n_second"] == 2


def test_walk_forward_mixed_is_not_both_positive():
    precomputed = [(1.0, 0.5, 0.6, 0.0), (1.0, 0.5, 0.6, 0.0),
                   (1.0, 0.6, 0.5, 0.0), (1.0, 0.6, 0.5, 0.0)]
    wf = val._walk_forward(precomputed)
    assert wf["wf_first"] > 0
    assert wf["wf_second"] < 0
    assert wf["both_positive"] is False


def _whale_trades_with_real_spikes():
    """4개 스파이크(경고z>2) 유발 — 시간대별 20건 baseline + 1건 대형체결, 마지막에 그리드
    연장용 filler 1건. run_family 실제 라벨 파이프라인(스파이크→가격그리드→forward_return)
    타는 유일한 fixture — 다른 테스트는 스파이크 없이 blocked 경로만 탐."""
    rows = []
    ts = 0.0
    for _ in range(4):
        for _ in range(20):
            rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                         "size": 10.0, "notional_usd": 5.0, "family": "news"})
            ts += 1.0
        rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                     "size": 2000.0, "notional_usd": 1000.0, "family": "news"})
        ts += 1.0
    rows.append({"ts": ts + 300.0, "condition_id": "c1", "side": "BUY", "price": 0.5,
                "size": 10.0, "notional_usd": 5.0, "family": "news"})
    return pd.DataFrame(rows)


def test_run_family_includes_walk_forward_per_horizon():
    r = val.run_family("news", _whale_trades_with_real_spikes())
    assert r["blocked"] is False
    for hv in r["horizons"].values():
        wf = hv["walk_forward"]
        assert set(wf) == {"wf_first", "wf_second", "n_first", "n_second", "both_positive"}
        assert wf["n_first"] + wf["n_second"] == hv["n_events"]


def test_compute_report_gates_survivors_on_walk_forward():
    rep = val.compute_report(_whale_trades_with_real_spikes(), ["2026-07-21"])
    pool = rep["pools"][0]
    assert "survivors_before_walk_forward" in pool
    # survivors(최종)는 전부 walk_forward 게이트 통과분의 부분집합이어야 함
    assert set(pool["survivors"]) <= set(pool["survivors_before_walk_forward"])
    assert pool["n_survivors"] == len(pool["survivors"])
