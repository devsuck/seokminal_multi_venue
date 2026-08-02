from unittest.mock import patch

import pandas as pd

import research.run_polymarket_sharp_wallet_validate as val


def test_run_bucket_blocked_when_no_labels():
    labels = pd.DataFrame(columns=["ts", "condition_id", "horizon_s", "entry_price",
                                    "exit_price", "direction", "forward_return", "convergence_bucket"])
    result = val.run_bucket(1, labels)
    assert result["blocked"] is True
    assert result["bucket"] == 1


def test_run_bucket_blocked_when_below_min_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1} for i in range(5)]
    labels = pd.DataFrame(rows)
    result = val.run_bucket(1, labels)
    assert result["blocked"] is True


def test_run_bucket_computes_pvalue_when_enough_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.55, "direction": 1.0, "forward_return": 0.1,
             "convergence_bucket": 2} for i in range(15)]
    labels = pd.DataFrame(rows)
    result = val.run_bucket(2, labels)
    assert result["blocked"] is False
    assert "30s" in result["horizons"]
    assert result["horizons"]["30s"]["n_events"] == 15
    assert result["horizons"]["30s"]["random"]["p_value"] is not None


def test_main_handles_no_data_dir_without_crash(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        val.main()  # 예외 없이 끝나야 함(전 버킷 BLOCKED 출력)


def test_add_score_tercile_splits_into_three_groups():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1, "score": float(i * 10)} for i in range(9)]
    labels = pd.DataFrame(rows)
    out = val.add_score_tercile(labels)
    assert set(out["score_tercile"].astype(str)) == {"low", "mid", "high"}
    assert out["score_tercile"].value_counts()["low"] == 3


def test_add_score_tercile_none_when_all_scores_nan():
    rows = [{"ts": 0.0, "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1, "score": float("nan")}]
    labels = pd.DataFrame(rows)
    out = val.add_score_tercile(labels)
    assert out["score_tercile"].iloc[0] is None


def test_run_score_tercile_blocked_when_no_labels():
    labels = pd.DataFrame(columns=["ts", "condition_id", "horizon_s", "entry_price",
                                    "exit_price", "direction", "forward_return",
                                    "convergence_bucket", "score", "score_tercile"])
    result = val.run_score_tercile("high", labels)
    assert result["blocked"] is True
    assert result["tercile"] == "high"


def test_run_score_tercile_blocked_when_below_min_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1, "score": 80.0, "score_tercile": "high"} for i in range(5)]
    labels = pd.DataFrame(rows)
    result = val.run_score_tercile("high", labels)
    assert result["blocked"] is True


def test_run_score_tercile_computes_pvalue_when_enough_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.55, "direction": 1.0, "forward_return": 0.1,
             "convergence_bucket": 2, "score": 80.0, "score_tercile": "high"} for i in range(15)]
    labels = pd.DataFrame(rows)
    result = val.run_score_tercile("high", labels)
    assert result["blocked"] is False
    assert "30s" in result["horizons"]
    assert result["horizons"]["30s"]["n_events"] == 15
    assert result["horizons"]["30s"]["random"]["p_value"] is not None


def _sharp_trades_min():
    # 소수 sharp anchor — build_convergence_count가 anchor를 만들지만 라벨이 MIN_EVENTS
    # 미달이라 그룹은 전부 BLOCKED(구조 검증용, 생존자 0 예상).
    return pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "price": 0.5, "size": 100.0,
         "proxy_wallet": "w1", "notional_usd": 50.0, "is_sharp_wallet": True,
         "wallet_rank": 1, "wallet_pnl": 100.0, "outcome_index": 0},
        {"ts": 10.0, "condition_id": "c2", "side": "BUY", "price": 0.5, "size": 100.0,
         "proxy_wallet": "w2", "notional_usd": 80.0, "is_sharp_wallet": True,
         "wallet_rank": 2, "wallet_pnl": 200.0, "outcome_index": 1},
    ])


def test_compute_report_no_data_returns_no_data_verdict():
    trades = pd.DataFrame(columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl", "outcome_index"])
    rep = val.compute_report(trades, [])
    assert rep["hypothesis"] == "polymarket_sharp_wallet"
    assert rep["verdict"] == "no_data"
    assert rep["n_anchors"] == 0
    assert rep["groups"] == []
    assert rep["pools"] == []


def test_compute_report_two_separate_bhfdr_pools_and_verdict():
    rep = val.compute_report(_sharp_trades_min(), ["2026-07-21"])
    assert rep["n_anchors"] == 2
    assert [p["name"] for p in rep["pools"]] == ["bucket", "score_tercile"]
    for p in rep["pools"]:
        assert set(p) >= {"name", "alpha", "n_tested", "n_survivors", "survivors", "threshold"}
    # 표본 부족 → 생존자 0 → no_edge
    assert rep["verdict"] == "no_edge"
    assert all("group" in g for g in rep["groups"])


def test_load_and_report_smoke_no_data(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        rep = val.load_and_report()
    assert rep["verdict"] == "no_data"
