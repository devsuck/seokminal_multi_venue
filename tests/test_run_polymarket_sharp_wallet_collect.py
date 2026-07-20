import datetime as dt
import json
from unittest.mock import patch

import pytest

import research.run_polymarket_sharp_wallet_collect as runner


def _trade(cid="c1", ts=100.0, tx="tx1", side="BUY", price=0.5, size=1000.0, wallet="0xsharp"):
    return {
        "conditionId": cid, "timestamp": ts, "transactionHash": tx,
        "side": side, "price": price, "size": size, "proxyWallet": wallet,
        "asset": "tok1", "title": "t", "slug": "s", "outcome": "Yes", "name": "trader1",
    }


def test_filter_new_trades_marks_sharp_wallet_trade_as_anchor_and_extends_watch_until():
    trades = [_trade(cid="c1", ts=100.0, wallet="0xsharp")]  # notional = 0.5*1000 = 500
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 10000.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert out[0]["is_sharp_wallet"] is True
    assert out[0]["wallet_rank"] == 1
    assert out[0]["wallet_pnl"] == 10000.0
    assert out[0]["notional_usd"] == pytest.approx(500.0)
    assert watch_until["c1"] == pytest.approx(100.0 + runner.MAX_HORIZON_S)


def test_filter_new_trades_drops_sharp_wallet_trade_below_min_notional():
    trades = [_trade(cid="c1", ts=100.0, wallet="0xsharp", price=0.5, size=10.0)]  # notional = 5.0
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 10000.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert out == []
    assert watch_until == {}


def test_filter_new_trades_keeps_context_trade_within_watch_until():
    trades = [_trade(cid="c1", ts=150.0, wallet="0xnobody", tx="ctx1")]
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, {}, {"c1": 200.0}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert out[0]["is_sharp_wallet"] is False
    assert out[0]["wallet_rank"] is None
    assert out[0]["wallet_pnl"] is None


def test_filter_new_trades_drops_trade_outside_watch_until_and_not_sharp():
    trades = [_trade(cid="c1", ts=250.0, wallet="0xnobody", tx="late1")]
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, {}, {"c1": 200.0}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert out == []


def test_filter_new_trades_skips_older_than_last_seen_ts():
    trades = [_trade(ts=50.0, tx="old", wallet="0xsharp"), _trade(ts=150.0, tx="new", wallet="0xsharp")]
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 1.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=100.0, seen_hashes=[],
    )
    assert [t["transactionHash"] for t in out] == ["new"]
    assert last_ts == 150.0


def test_filter_new_trades_skips_already_seen_hash():
    trades = [_trade(tx="dup1", wallet="0xsharp"), _trade(tx="dup1", wallet="0xsharp")]
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 1.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert hashes.count("dup1") == 1


def test_filter_new_trades_ring_buffer_caps_at_size():
    seen = [f"old{i}" for i in range(runner.DEDUP_HASH_RING_SIZE)]
    trades = [_trade(tx="new1", wallet="0xsharp")]
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 1.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=seen,
    )
    assert len(hashes) == runner.DEDUP_HASH_RING_SIZE
    assert hashes[-1] == "new1"


def test_prune_stale_watch_removes_entries_older_than_horizon():
    watch_until = {"c1": 100.0, "c2": 1000.0}
    now = 100.0 + runner.MAX_HORIZON_S + 1.0
    result = runner.prune_stale_watch(watch_until, now)
    assert result == {"c2": 1000.0}


def test_prune_stale_watch_keeps_recent_entries():
    watch_until = {"c1": 100.0}
    now = 100.0
    result = runner.prune_stale_watch(watch_until, now)
    assert result == {"c1": 100.0}


def test_append_trades_writes_jsonl_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_trades([_trade(tx="a"), _trade(tx="b")])
        path = tmp_path / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["transactionHash"] == "a"


def test_append_trades_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_trades([])
    assert list(tmp_path.iterdir()) == []


def test_run_forever_refreshes_leaderboard_only_after_interval():
    refresh_calls = []

    def fake_leaderboard():
        refresh_calls.append(1)
        return {"0xsharp": {"rank": 1, "pnl": 1.0}}

    fake_time = [1000.0]

    def fake_time_fn():
        return fake_time[0]

    def fake_sleep(_):
        fake_time[0] += 1.0

    with patch("time.time", side_effect=fake_time_fn), patch("time.sleep", side_effect=fake_sleep):
        runner.run_forever(
            fetch_fn=lambda: [], leaderboard_fn=fake_leaderboard, append_fn=lambda t: None,
            poll_interval_s=1.0, leaderboard_refresh_interval_s=1000.0, max_cycles=3,
        )
    assert len(refresh_calls) == 1  # 최초 1회만, interval 안 지났으니 재조회 없음


def test_run_forever_polls_and_appends_new_trades_across_cycles():
    appended = []
    fetch_calls = [[_trade(ts=100.0, tx="a", wallet="0xsharp")], [_trade(ts=200.0, tx="b", wallet="0xsharp")]]

    def fake_fetch():
        return fetch_calls.pop(0) if fetch_calls else []

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=fake_fetch, leaderboard_fn=lambda: {"0xsharp": {"rank": 1, "pnl": 1.0}},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, leaderboard_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a", "b"]


def test_run_forever_continues_after_fetch_exception():
    appended = []
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("boom")
        return [_trade(ts=100.0, tx="a", wallet="0xsharp")]

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=flaky_fetch, leaderboard_fn=lambda: {"0xsharp": {"rank": 1, "pnl": 1.0}},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, leaderboard_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a"]
