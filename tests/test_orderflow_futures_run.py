from unittest.mock import patch

from research.hypotheses.orderflow_futures import (
    run_all_hypotheses,
    run_signal_hypothesis,
    run_stop_run_hypothesis,
)


def _write_deltas(tmp_path, name, deltas):
    import json
    path = tmp_path / name
    with path.open("w") as f:
        for d in deltas:
            f.write(json.dumps(d) + "\n")
    return str(path)


def _fd(bucket_ts, price, side, vol):
    return {"type": "footprint_delta", "bucket_ts": bucket_ts, "price": price, "side": side, "delta_vol": vol}


def test_run_signal_hypothesis_blocked_when_no_data(tmp_path):
    result = run_signal_hypothesis("NQ", "footprint_imbalance", [], write_report=False)
    assert result["blocked"] is True
    assert "no delta data" in result["reason"]


def test_run_signal_hypothesis_blocked_when_too_few_bars(tmp_path):
    deltas = [_fd(0.0, 100.0, "buy", 5.0)]
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    result = run_signal_hypothesis("NQ", "footprint_imbalance", [path], write_report=False)
    assert result["blocked"] is True


def test_run_signal_hypothesis_returns_strategy_and_random_when_enough_bars(tmp_path):
    deltas = []
    for i in range(20):
        b = float(i * 60)
        if i % 3 == 0:
            deltas.append(_fd(b, 100.0 + i, "buy", 9.0))
            deltas.append(_fd(b, 100.0 + i, "sell", 1.0))
        else:
            deltas.append(_fd(b, 100.0 + i, "buy", 1.0))
            deltas.append(_fd(b, 100.0 + i, "sell", 1.0))
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    result = run_signal_hypothesis("NQ", "footprint_imbalance", [path], n_runs=20, write_report=False)
    assert result["blocked"] is False
    assert "strategy" in result and "random" in result


def test_run_signal_hypothesis_unknown_signal_name_raises(tmp_path):
    import pytest
    deltas = [_fd(float(i * 60), 100.0, "buy", 1.0) for i in range(15)]
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    with pytest.raises(ValueError):
        run_signal_hypothesis("NQ", "not_a_real_signal", [path], write_report=False)


def test_run_stop_run_hypothesis_blocked_when_no_events(tmp_path):
    deltas = [_fd(float(i * 60), 100.0, "buy", 1.0) for i in range(15)]
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    result = run_stop_run_hypothesis("NQ", [path], write_report=False)
    assert result["blocked"] is True


def test_run_all_hypotheses_applies_bh_fdr_across_all_symbol_signal_pairs(tmp_path):
    deltas = []
    for i in range(20):
        b = float(i * 60)
        deltas.append(_fd(b, 100.0 + i, "buy", 9.0 if i % 3 == 0 else 1.0))
        deltas.append(_fd(b, 100.0 + i, "sell", 1.0 if i % 3 == 0 else 1.0))
    nq_path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    mnq_path = _write_deltas(tmp_path, "MNQ.jsonl", deltas)

    result = run_all_hypotheses(
        {"NQ": [nq_path], "MNQ": [mnq_path]}, n_runs=20,
    )
    assert "results" in result and "bh_fdr" in result
    assert result["bh_fdr"]["alpha"] == 0.1
    # 6신호(footprint_imbalance/absorption/cvd_divergence/wall_proximity/iceberg_refill/stop_run) x 2심볼
    assert len(result["results"]) == 12
    # heatmap_delta 없는 합성데이터라 wall_proximity/iceberg_refill/stop_run은 BLOCKED됨 ->
    # p-value 있는 항목만 BH-FDR 입력에 들어감. survivors는 그 항목 수와 정확히 일치해야 함.
    assert len(result["bh_fdr"]["survivors"]) == len(result["bh_fdr"]["keys"])
    assert len(result["bh_fdr"]["keys"]) > 0  # footprint_imbalance/absorption/cvd_divergence는 데이터 충분 -> BLOCKED 아님
