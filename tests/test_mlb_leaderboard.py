import pandas as pd

from research.mlb_specialist.leaderboard import wallet_mlb_stats, rank_specialists


def _trades(rows):
    return pd.DataFrame(rows, columns=["proxy_wallet", "condition_id", "side", "price", "size", "notional_usd", "ts"])


def _t(w, cid, side, price, size, ts):
    return {"proxy_wallet": w, "condition_id": cid, "side": side, "price": price,
            "size": size, "notional_usd": price * size, "ts": ts}


# 마켓 정산: winning_side + resolved_ts
RES = {
    "m1": {"winning_side": "YES", "resolved_ts": 100.0},
    "m2": {"winning_side": "NO", "resolved_ts": 200.0},
    "m3": {"winning_side": "YES", "resolved_ts": 300.0},
}


def test_wallet_stats_pnl_winrate_roi():
    trades = _trades([
        _t("w1", "m1", "YES", 0.5, 100, 10.0),   # 승: (1-0.5)*100 = +50, notional 50
        _t("w1", "m2", "YES", 0.4, 100, 20.0),   # 패(winning=NO): (0-0.4)*100 = -40, notional 40
    ])
    out = wallet_mlb_stats(trades, RES, total_vol={"w1": 180.0})
    r = out[out["proxy_wallet"] == "w1"].iloc[0]
    assert r["mlb_n"] == 2
    assert r["mlb_pnl"] == 50.0 - 40.0            # +10
    assert r["mlb_winrate"] == 0.5                # 1/2
    assert r["mlb_notional"] == 90.0              # 50+40
    assert r["mlb_roi"] == pytest_approx(10.0 / 90.0)
    assert r["mlb_specialization"] == pytest_approx(90.0 / 180.0)


def test_walk_forward_excludes_unresolved_as_of():
    trades = _trades([
        _t("w1", "m1", "YES", 0.5, 100, 10.0),   # resolved_ts 100
        _t("w1", "m3", "YES", 0.5, 100, 10.0),   # resolved_ts 300 — as_of=150이면 제외
    ])
    out = wallet_mlb_stats(trades, RES, total_vol={"w1": 200.0}, as_of=150.0)
    r = out[out["proxy_wallet"] == "w1"].iloc[0]
    assert r["mlb_n"] == 1                        # m3(정산 300>150) 제외


def test_unresolved_market_ignored():
    trades = _trades([_t("w1", "unknown_market", "YES", 0.5, 100, 10.0)])
    out = wallet_mlb_stats(trades, RES, total_vol={"w1": 50.0})
    assert out.empty or out.iloc[0]["mlb_n"] == 0


def test_rank_specialists_by_each_metric():
    stats = pd.DataFrame([
        {"proxy_wallet": "big",  "mlb_pnl": 100.0, "mlb_winrate": 0.4, "mlb_roi": 0.05, "mlb_n": 20, "mlb_specialization": 0.9},
        {"proxy_wallet": "sharp","mlb_pnl": 30.0,  "mlb_winrate": 0.7, "mlb_roi": 0.30, "mlb_n": 20, "mlb_specialization": 0.9},
        {"proxy_wallet": "mid",  "mlb_pnl": 50.0,  "mlb_winrate": 0.5, "mlb_roi": 0.10, "mlb_n": 20, "mlb_specialization": 0.9},
    ])
    assert rank_specialists(stats, "pnl", n=2, min_bets=10, min_spec=0.5) == ["big", "mid"]
    assert rank_specialists(stats, "winrate", n=2, min_bets=10, min_spec=0.5) == ["sharp", "mid"]
    assert rank_specialists(stats, "roi", n=2, min_bets=10, min_spec=0.5) == ["sharp", "mid"]


def test_rank_gate_min_bets_and_spec():
    stats = pd.DataFrame([
        {"proxy_wallet": "few",   "mlb_pnl": 999.0, "mlb_winrate": 1.0, "mlb_roi": 1.0, "mlb_n": 3,  "mlb_specialization": 0.9},
        {"proxy_wallet": "casual","mlb_pnl": 500.0, "mlb_winrate": 0.9, "mlb_roi": 0.9, "mlb_n": 20, "mlb_specialization": 0.2},
        {"proxy_wallet": "ok",    "mlb_pnl": 10.0,  "mlb_winrate": 0.5, "mlb_roi": 0.1, "mlb_n": 20, "mlb_specialization": 0.8},
    ])
    # few=표본부족, casual=특화도부족 → ok만 통과
    assert rank_specialists(stats, "pnl", n=5, min_bets=10, min_spec=0.5) == ["ok"]


def pytest_approx(v):
    import pytest
    return pytest.approx(v)
