from research.run_mlb_specialist_collect import filter_mlb_trades, _map_trade


def _raw(cid, h, wallet="w1", price=0.5, size=100, ts=1.0, side="BUY", outcome="Yes"):
    return {"conditionId": cid, "transactionHash": h, "proxyWallet": wallet,
            "price": price, "size": size, "timestamp": ts, "side": side, "outcome": outcome}


def test_filter_keeps_mlb_and_dedups():
    mlb = {"mlb1", "mlb2"}
    trades = [_raw("mlb1", "h1"), _raw("nba1", "h2"), _raw("mlb2", "h3"), _raw("mlb1", "h1")]
    out, seen = filter_mlb_trades(trades, mlb, [])
    assert [t["condition_id"] for t in out] == ["mlb1", "mlb2"]  # nba 제외, h1 중복 드롭
    assert "h1" in seen and "h3" in seen and "h2" not in seen


def test_filter_respects_prior_seen():
    out, _ = filter_mlb_trades([_raw("mlb1", "h1")], {"mlb1"}, ["h1"])
    assert out == []


def test_filter_empty_mlb_set():
    out, _ = filter_mlb_trades([_raw("mlb1", "h1")], set(), [])
    assert out == []


def test_map_trade_fields():
    m = _map_trade(_raw("mlb1", "h1", price=0.4, size=50, outcome="No"))
    assert m["condition_id"] == "mlb1"
    assert m["notional_usd"] == 20.0
    assert m["outcome"] == "No"
    assert m["proxy_wallet"] == "w1"
    assert m["transactionHash"] == "h1"
