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
