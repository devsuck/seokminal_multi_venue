import json

import pandas as pd
import pytest

import research.hypotheses.polymarket_sharp_wallet as psw
from research.hypotheses.polymarket_sharp_wallet import (
    build_convergence_count,
    build_convergence_score,
    build_labels_multi_horizon,
    build_price_series,
    load_sharp_wallet_trades,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _raw_row(cid="c1", ts=1.0, side="BUY", price=0.5, size=100.0, wallet="0xsharp",
             is_sharp=True, rank=1, pnl=1000.0, outcome_index=0):
    return {
        "conditionId": cid, "timestamp": ts, "side": side, "price": price, "size": size,
        "proxyWallet": wallet, "notional_usd": price * size, "is_sharp_wallet": is_sharp,
        "wallet_rank": rank if is_sharp else None, "wallet_pnl": pnl if is_sharp else None,
        "transactionHash": f"tx{ts}", "outcomeIndex": outcome_index,
    }


def _trade_row(ts, cid="c1", wallet="w1", side="BUY", is_sharp=True, notional=100.0, price=0.5,
               outcome_index=0):
    return {
        "ts": ts, "condition_id": cid, "side": side, "price": price, "size": notional / price,
        "proxy_wallet": wallet, "notional_usd": notional, "is_sharp_wallet": is_sharp,
        "wallet_rank": 1 if is_sharp else None, "wallet_pnl": 100.0 if is_sharp else None,
        "outcome_index": outcome_index,
    }


def test_load_sharp_wallet_trades_reads_and_preserves_precomputed_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-20.jsonl", [
        _raw_row(ts=2.0, wallet="0xsharp", is_sharp=True, rank=3, pnl=200.0),
        _raw_row(ts=1.0, wallet="0xother", is_sharp=False),
    ])
    df = load_sharp_wallet_trades(["2026-07-20"])
    assert list(df["ts"]) == [1.0, 2.0]
    assert bool(df.iloc[0]["is_sharp_wallet"]) is False
    assert bool(df.iloc[1]["is_sharp_wallet"]) is True
    assert df.iloc[1]["wallet_rank"] == 3
    assert df.iloc[1]["wallet_pnl"] == 200.0
    assert df.iloc[1]["outcome_index"] == 0


def test_load_sharp_wallet_trades_passes_through_outcome_index_as_is(tmp_path, monkeypatch):
    # outcomeIndex는 정규화 없이 원본 그대로(999 비이진 센티널/누락 포함) 통과시킨다.
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-20.jsonl", [
        _raw_row(ts=1.0, cid="c1", outcome_index=1),
        _raw_row(ts=2.0, cid="c2", outcome_index=999),
    ])
    df = load_sharp_wallet_trades(["2026-07-20"])
    assert df.iloc[0]["outcome_index"] == 1
    assert df.iloc[1]["outcome_index"] == 999


def test_load_sharp_wallet_trades_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-19.jsonl", [_raw_row(ts=1.0)])
    _write_jsonl(tmp_path / "2026-07-20.jsonl", [_raw_row(ts=2.0)])
    df = load_sharp_wallet_trades(["2026-07-19", "2026-07-20"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_sharp_wallet_trades_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    df = load_sharp_wallet_trades(["2020-01-01"])
    assert df.empty


def test_build_convergence_count_counts_distinct_wallets_within_window():
    df = pd.DataFrame([
        _trade_row(ts=0.0, cid="c1", wallet="w1"),
        _trade_row(ts=300.0, cid="c2", wallet="w2"),
        _trade_row(ts=650.0, cid="c3", wallet="w3"),
    ])
    out = build_convergence_count(df)
    counts = dict(zip(out["ts"], out["convergence_count"]))
    assert counts[0.0] == 1        # window [-600,0]: only itself
    assert counts[300.0] == 2      # window [-300,300]: w1(ts=0) + w2(ts=300)
    assert counts[650.0] == 2      # window [50,650]: w2(ts=300) + w3(ts=650), w1(ts=0) excluded


def test_build_convergence_count_ignores_context_trades():
    df = pd.DataFrame([
        _trade_row(ts=0.0, cid="c1", wallet="w1", is_sharp=True),
        _trade_row(ts=10.0, cid="c1", wallet="w9", is_sharp=False),
    ])
    out = build_convergence_count(df)
    assert len(out) == 1
    assert out.iloc[0]["convergence_count"] == 1


def test_build_convergence_count_caps_at_max_bucket():
    rows = [_trade_row(ts=float(i), cid=f"c{i}", wallet=f"w{i}") for i in range(5)]
    df = pd.DataFrame(rows)
    out = build_convergence_count(df)
    last = out.iloc[-1]
    assert last["convergence_count"] == 5
    assert last["convergence_bucket"] == psw.MAX_CONVERGENCE_BUCKET


def test_build_convergence_count_carries_outcome_index():
    df = pd.DataFrame([_trade_row(ts=0.0, cid="c1", wallet="w1", outcome_index=1)])
    out = build_convergence_count(df)
    assert out.iloc[0]["outcome_index"] == 1


def test_build_convergence_count_empty_when_no_anchors():
    df = pd.DataFrame([_trade_row(ts=0.0, wallet="w1", is_sharp=False)])
    out = build_convergence_count(df)
    assert out.empty


def test_build_price_series_ffill_grid():
    df = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 0, "price": 0.5},
        {"ts": 12.0, "condition_id": "c1", "outcome_index": 0, "price": 0.6},
    ])
    series = build_price_series(df, "c1", 0)
    assert series.loc[0.0] == pytest.approx(0.5)
    assert series.loc[5.0] == pytest.approx(0.5)
    assert series.loc[10.0] == pytest.approx(0.5)
    assert series.loc[15.0] == pytest.approx(0.6)


def test_build_price_series_empty_for_unknown_condition():
    df = pd.DataFrame([{"ts": 0.0, "condition_id": "c1", "outcome_index": 0, "price": 0.5}])
    series = build_price_series(df, "unknown", 0)
    assert series.empty


def test_build_price_series_filters_other_outcome_index():
    # 같은 condition_id라도 outcome_index 다른 토큰(No)의 체결은 섞이면 안 된다.
    df = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 0, "price": 0.5},
        {"ts": 5.0, "condition_id": "c1", "outcome_index": 1, "price": 0.9},
        {"ts": 10.0, "condition_id": "c1", "outcome_index": 0, "price": 0.5},
    ])
    series = build_price_series(df, "c1", 0)
    assert series.loc[5.0] == pytest.approx(0.5)


def test_build_labels_multi_horizon_computes_forward_return_and_carries_bucket():
    price = pd.Series([0.5, 0.5, 0.6, 0.6, 0.7, 0.7, 0.7],
                       index=[0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 0, "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 2,
         "convergence_bucket": 2},
    ])
    labels = build_labels_multi_horizon(anchors, {("c1", 0): price}, horizons=[10, 30])
    row10 = labels[labels["horizon_s"] == 10].iloc[0]
    assert row10["forward_return"] == pytest.approx((0.6 - 0.5) / 0.5)
    assert row10["convergence_bucket"] == 2
    row30 = labels[labels["horizon_s"] == 30].iloc[0]
    assert row30["forward_return"] == pytest.approx((0.7 - 0.5) / 0.5)


def test_build_labels_multi_horizon_excludes_missing_condition():
    price = pd.Series([0.5], index=[0.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "unknown", "outcome_index": 0, "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    labels = build_labels_multi_horizon(anchors, {("c1", 0): price}, horizons=[10])
    assert labels.empty


def test_build_labels_multi_horizon_excludes_non_binary_outcome_index():
    # outcome_index=999(비이진 센티널)는 어느 토큰 가격인지 알 수 없어 제외.
    price = pd.Series([0.5, 0.6], index=[0.0, 10.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 999, "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    labels = build_labels_multi_horizon(anchors, {("c1", 0): price}, horizons=[10])
    assert labels.empty


def test_build_labels_multi_horizon_uses_matching_outcome_index_series():
    # c1의 Yes(0)/No(1) 시계열이 따로 있을 때 anchor의 outcome_index로만 조회.
    price_yes = pd.Series([0.5, 0.6], index=[0.0, 10.0])
    price_no = pd.Series([0.9, 0.1], index=[0.0, 10.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 1, "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    labels = build_labels_multi_horizon(
        anchors, {("c1", 0): price_yes, ("c1", 1): price_no}, horizons=[10])
    assert labels.iloc[0]["forward_return"] == pytest.approx((0.1 - 0.9) / 0.9)


def test_build_convergence_score_bounded_percentiles_and_liquidity_window():
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 50.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
        {"ts": 1000.0, "condition_id": "c2", "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w2", "convergence_count": 1,
         "convergence_bucket": 1},
        {"ts": 2000.0, "condition_id": "c3", "side": "BUY", "direction": 1.0,
         "notional_usd": 200.0, "proxy_wallet": "w3", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    trades = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "proxy_wallet": "w1", "notional_usd": 50.0,
         "is_sharp_wallet": True, "wallet_pnl": 100.0},
        {"ts": 100.0, "condition_id": "c1", "proxy_wallet": "ctx1", "notional_usd": 50.0,
         "is_sharp_wallet": False, "wallet_pnl": None},
        {"ts": 301.0, "condition_id": "c1", "proxy_wallet": "ctx1b", "notional_usd": 999.0,
         "is_sharp_wallet": False, "wallet_pnl": None},  # 윈도우(0~300) 밖 — 제외돼야 함
        {"ts": 1000.0, "condition_id": "c2", "proxy_wallet": "w2", "notional_usd": 100.0,
         "is_sharp_wallet": True, "wallet_pnl": 500.0},
        {"ts": 1100.0, "condition_id": "c2", "proxy_wallet": "ctx2", "notional_usd": 100.0,
         "is_sharp_wallet": False, "wallet_pnl": None},
        {"ts": 2000.0, "condition_id": "c3", "proxy_wallet": "w3", "notional_usd": 200.0,
         "is_sharp_wallet": True, "wallet_pnl": 1000.0},
        {"ts": 2100.0, "condition_id": "c3", "proxy_wallet": "ctx3", "notional_usd": 200.0,
         "is_sharp_wallet": False, "wallet_pnl": None},
    ])
    out = build_convergence_score(trades, anchors)

    assert list(out["pnl_sum_raw"]) == [100.0, 500.0, 1000.0]
    assert list(out["liquidity_raw"]) == [100.0, 200.0, 400.0]  # 윈도우 밖 999는 제외

    scores = list(out["score"])
    # wallet_count는 3개 anchor 모두 convergence_count=1로 동석 -> percentile 50 고정.
    # pnl/notional/liquidity는 각각 단조증가 -> 0/50/100.
    assert scores[0] == pytest.approx((50.0 + 0.0 + 0.0 + 0.0) / 4)
    assert scores[1] == pytest.approx((50.0 + 50.0 + 50.0 + 50.0) / 4)
    assert scores[2] == pytest.approx((50.0 + 100.0 + 100.0 + 100.0) / 4)


def test_build_convergence_score_nan_when_fewer_than_two_anchors():
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 50.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    trades = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "proxy_wallet": "w1", "notional_usd": 50.0,
         "is_sharp_wallet": True, "wallet_pnl": 100.0},
    ])
    out = build_convergence_score(trades, anchors)
    assert pd.isna(out["score"].iloc[0])


def test_build_convergence_score_empty_anchors_returns_empty():
    trades = pd.DataFrame(columns=["ts", "condition_id", "proxy_wallet", "notional_usd",
                                    "is_sharp_wallet", "wallet_pnl"])
    anchors = pd.DataFrame(columns=["ts", "condition_id", "side", "direction",
                                     "notional_usd", "proxy_wallet", "convergence_count",
                                     "convergence_bucket"])
    out = build_convergence_score(trades, anchors)
    assert out.empty
    assert "score" in out.columns


def test_build_labels_multi_horizon_carries_score_when_present():
    price = pd.Series([0.5, 0.6], index=[0.0, 10.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 0, "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1, "score": 87.5},
    ])
    labels = build_labels_multi_horizon(anchors, {("c1", 0): price}, horizons=[10])
    assert labels.iloc[0]["score"] == pytest.approx(87.5)


def test_build_labels_multi_horizon_score_nan_when_anchors_lack_score_column():
    price = pd.Series([0.5, 0.6], index=[0.0, 10.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "outcome_index": 0, "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    labels = build_labels_multi_horizon(anchors, {("c1", 0): price}, horizons=[10])
    assert pd.isna(labels.iloc[0]["score"])
