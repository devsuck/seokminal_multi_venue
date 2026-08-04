import pandas as pd

from research.hypotheses.polymarket_whale_coincidence import build_coincidence_signal


def _spike(ts, wallet, direction=1.0, cid="c1", family="news", z=3.0):
    return {"ts": ts, "condition_id": cid, "family": family, "side": "BUY", "direction": direction,
            "notional_usd": 1000.0, "notional_z": z, "proxy_wallet": wallet, "outcome_index": 0}


def test_single_wallet_repeated_never_confirms():
    spikes = pd.DataFrame([_spike(0.0, "w1"), _spike(10.0, "w1"), _spike(20.0, "w1")])
    out = build_coincidence_signal(spikes, window_s=60.0, min_wallets=2)
    assert out.empty


def test_two_distinct_wallets_within_window_confirms_at_second_ts():
    spikes = pd.DataFrame([_spike(0.0, "w1"), _spike(30.0, "w2")])
    out = build_coincidence_signal(spikes, window_s=60.0, min_wallets=2)
    assert len(out) == 1
    assert out.iloc[0]["ts"] == 30.0
    assert out.iloc[0]["n_wallets"] == 2
    assert set(out.iloc[0]["member_wallets"]) == {"w1", "w2"}


def test_second_wallet_outside_window_does_not_confirm():
    spikes = pd.DataFrame([_spike(0.0, "w1"), _spike(120.0, "w2")])
    out = build_coincidence_signal(spikes, window_s=60.0, min_wallets=2)
    assert out.empty


def test_opposite_direction_does_not_count_toward_same_cluster():
    spikes = pd.DataFrame([_spike(0.0, "w1", direction=1.0), _spike(10.0, "w2", direction=-1.0)])
    out = build_coincidence_signal(spikes, window_s=60.0, min_wallets=2)
    assert out.empty


def test_different_market_does_not_count_toward_same_cluster():
    spikes = pd.DataFrame([_spike(0.0, "w1", cid="c1"), _spike(10.0, "w2", cid="c2")])
    out = build_coincidence_signal(spikes, window_s=60.0, min_wallets=2)
    assert out.empty


def test_cluster_confirmed_once_skips_past_confirming_trade():
    # w1@0, w2@10(확정), w3@15 -- 확정 이후 다음 앵커는 index 2(w3)부터 재시작, 단독이라 미확정.
    spikes = pd.DataFrame([_spike(0.0, "w1"), _spike(10.0, "w2"), _spike(15.0, "w3")])
    out = build_coincidence_signal(spikes, window_s=60.0, min_wallets=2)
    assert len(out) == 1
    assert out.iloc[0]["ts"] == 10.0


def test_empty_input_returns_empty_with_expected_columns():
    out = build_coincidence_signal(pd.DataFrame())
    assert out.empty
    assert "n_wallets" in out.columns
