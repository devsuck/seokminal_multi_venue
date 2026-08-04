from unittest.mock import patch

import pandas as pd

import research.run_polymarket_whale_coincidence_validate as val


def test_compute_report_no_data_returns_no_data_verdict():
    df = pd.DataFrame(columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family", "outcome_index"])
    rep = val.compute_report(df, [])
    assert rep["hypothesis"] == "polymarket_whale_coincidence"
    assert rep["verdict"] == "no_data"
    assert rep["pools"] == []


def test_run_family_blocked_when_no_coincidence_cluster():
    # 단일 지갑만 반복 스파이크 -> 동조 클러스터 없음(min_wallets=2 미달) -> blocked.
    rows = []
    ts = 0.0
    for _ in range(4):
        for _ in range(20):
            rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                         "size": 10.0, "notional_usd": 5.0, "family": "news", "outcome_index": 0,
                         "proxy_wallet": "w1"})
            ts += 1.0
        rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                     "size": 2000.0, "notional_usd": 1000.0, "family": "news", "outcome_index": 0,
                     "proxy_wallet": "w1"})
        ts += 1.0
    df = pd.DataFrame(rows)
    result = val.run_family("news", df)
    assert result["blocked"] is True
    assert result["reason"] == "동조 클러스터 없음"


def test_run_family_with_coinciding_wallets_produces_labels():
    # 4개 스파이크 클러스터(서로 다른 지갑쌍) -> 동조 확정 -> forward_return 라벨까지 생성.
    rows = []
    ts = 0.0
    for pair in range(4):
        for _ in range(20):
            rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                         "size": 10.0, "notional_usd": 5.0, "family": "news", "outcome_index": 0,
                         "proxy_wallet": "baseline"})
            ts += 1.0
        rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                     "size": 2000.0, "notional_usd": 1000.0, "family": "news", "outcome_index": 0,
                     "proxy_wallet": f"w{pair}a"})
        ts += 5.0
        rows.append({"ts": ts, "condition_id": "c1", "side": "BUY", "price": 0.5,
                     "size": 2000.0, "notional_usd": 1000.0, "family": "news", "outcome_index": 0,
                     "proxy_wallet": f"w{pair}b"})
        ts += 1.0
    rows.append({"ts": ts + 300.0, "condition_id": "c1", "side": "BUY", "price": 0.5,
                "size": 10.0, "notional_usd": 5.0, "family": "news", "outcome_index": 0,
                "proxy_wallet": "baseline"})
    df = pd.DataFrame(rows)
    result = val.run_family("news", df)
    assert result["blocked"] is False
    assert all(hv["n_events"] > 0 for hv in result["horizons"].values())


def test_main_handles_no_data_dir_without_crash(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        val.main()
