import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_whale_collect as runner


def _trade(cid="c1", ts=100.0, tx="tx1", side="BUY", price=0.5, size=1000.0):
    return {
        "conditionId": cid, "timestamp": ts, "transactionHash": tx,
        "side": side, "price": price, "size": size,
        "proxyWallet": "0xabc", "asset": "tok1", "title": "t", "slug": "s",
        "outcome": "Yes", "name": "whale1",
    }


def test_filter_new_trades_keeps_only_target_condition_ids():
    trades = [_trade(cid="c1"), _trade(cid="c2", tx="tx2")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert out[0]["conditionId"] == "c1"
    assert out[0]["family"] == "news"


def test_filter_new_trades_skips_older_than_last_seen_ts():
    trades = [_trade(ts=50.0, tx="old"), _trade(ts=150.0, tx="new")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=100.0, seen_hashes=[],
    )
    assert [t["transactionHash"] for t in out] == ["new"]
    assert last_ts == 150.0


def test_filter_new_trades_skips_already_seen_hash():
    trades = [_trade(tx="dup1"), _trade(tx="dup1")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert hashes.count("dup1") == 1


def test_filter_new_trades_advances_last_seen_ts_to_max():
    trades = [_trade(ts=100.0, tx="a"), _trade(ts=300.0, tx="b"), _trade(ts=200.0, tx="c")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert last_ts == 300.0


def test_filter_new_trades_ring_buffer_caps_at_size():
    seen = [f"old{i}" for i in range(runner.DEDUP_HASH_RING_SIZE)]
    trades = [_trade(tx="new1")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=seen,
    )
    assert len(hashes) == runner.DEDUP_HASH_RING_SIZE
    assert hashes[-1] == "new1"


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


def test_run_forever_refreshes_market_list_only_after_interval():
    refresh_calls = []

    def fake_refresh():
        refresh_calls.append(1)
        return {"c1": "news"}

    fake_time = [1000.0]

    def fake_time_fn():
        return fake_time[0]

    def fake_sleep(_):
        fake_time[0] += 1.0

    with patch("time.time", side_effect=fake_time_fn), patch("time.sleep", side_effect=fake_sleep):
        runner.run_forever(
            fetch_fn=lambda: [], refresh_fn=fake_refresh, append_fn=lambda t: None,
            poll_interval_s=1.0, market_refresh_interval_s=1000.0, max_cycles=3,
        )
    assert len(refresh_calls) == 1  # 최초 1회만, interval 안 지났으니 재조회 없음


def test_run_forever_polls_and_appends_new_trades_across_cycles():
    appended = []
    fetch_calls = [[_trade(ts=100.0, tx="a")], [_trade(ts=200.0, tx="b")]]

    def fake_fetch():
        return fetch_calls.pop(0) if fetch_calls else []

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=fake_fetch, refresh_fn=lambda: {"c1": "news"},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, market_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a", "b"]


def test_run_forever_continues_after_fetch_exception():
    appended = []
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("boom")
        return [_trade(ts=100.0, tx="a")]

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=flaky_fetch, refresh_fn=lambda: {"c1": "news"},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, market_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a"]


def test_run_forever_fetch_keeps_running_when_market_refresh_keeps_failing():
    """2026-07-30 재현 버그: refresh_fn이 계속 실패하면(DNS 등) market_refresh_interval_s를
    매 사이클 넘겨서 refresh가 계속 재시도되는데, 예전엔 이게 fetch_fn까지 같은 try에
    묶여있어서 매 사이클 refresh 단계에서 raise → fetch_fn이 단 한 번도 안 불림.
    지금은 별개 try라 refresh가 매번 실패해도 fetch_fn은 매 사이클 정상 호출돼야 함."""
    appended = []
    fetch_calls = {"n": 0}

    def always_failing_refresh():
        raise ConnectionError("dns down")

    def counting_fetch():
        fetch_calls["n"] += 1
        return [_trade(ts=float(fetch_calls["n"]), tx=f"t{fetch_calls['n']}")]

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=counting_fetch, refresh_fn=always_failing_refresh,
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, market_refresh_interval_s=0.0, max_cycles=5,
        )
    assert fetch_calls["n"] == 5  # refresh가 매 사이클 실패해도 fetch는 5번 다 돎
    assert appended == []  # target_markets가 계속 {}라 필터에서 다 걸러짐(정상)


def test_run_forever_starts_even_when_initial_refresh_fails():
    """최초 refresh_fn() 호출은 예전엔 try 밖이라 실패하면 프로세스 자체가 죽었음
    (unguarded). 지금은 감싸져서 빈 target으로라도 루프가 시작돼야 함."""
    fetch_calls = {"n": 0}

    def counting_fetch():
        fetch_calls["n"] += 1
        return []

    def failing_refresh():
        raise ConnectionError("dns down")

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=counting_fetch, refresh_fn=failing_refresh,
            append_fn=lambda t: None,
            poll_interval_s=0.0, market_refresh_interval_s=1000.0, max_cycles=3,
        )
    assert fetch_calls["n"] == 3
