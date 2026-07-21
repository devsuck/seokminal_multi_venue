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
