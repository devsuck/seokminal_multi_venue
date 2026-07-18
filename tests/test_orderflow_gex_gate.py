from research.hypotheses.orderflow_gex_gate import (
    MAX_STALENESS_SEC,
    aggregate_net_gex,
    build_gex_gated_signals,
    build_gex_regime_series,
    nearest_gex_snapshot,
)


def _snap(ts, net_gexes):
    return {"updated_at": ts, "levels": [{"strike": 100.0 + i, "call_gex": 0.0, "put_gex": 0.0, "net_gex": n} for i, n in enumerate(net_gexes)]}


def test_aggregate_net_gex_sums_all_levels():
    snap = _snap(0.0, [1.5, -0.5, 2.0])
    assert aggregate_net_gex(snap) == 3.0


def test_nearest_gex_snapshot_picks_most_recent_at_or_before_ts():
    snaps = [_snap(0.0, [1.0]), _snap(60.0, [2.0]), _snap(120.0, [3.0])]
    result = nearest_gex_snapshot(snaps, ts=90.0)
    assert result["updated_at"] == 60.0


def test_nearest_gex_snapshot_returns_none_when_too_stale():
    snaps = [_snap(0.0, [1.0])]
    result = nearest_gex_snapshot(snaps, ts=1000.0, max_staleness_sec=300.0)
    assert result is None


def test_nearest_gex_snapshot_returns_none_when_no_snapshot_yet():
    result = nearest_gex_snapshot([], ts=100.0)
    assert result is None


def test_build_gex_regime_series_labels_negative_and_positive_and_stale():
    snaps = [_snap(0.0, [-5.0]), _snap(60.0, [5.0])]
    bucket_ts = [0.0, 60.0, 10_000.0]
    regimes = build_gex_regime_series(snaps, bucket_ts, max_staleness_sec=MAX_STALENESS_SEC)
    assert regimes == ["negative", "positive", None]


def test_build_gex_gated_signals_excludes_stale_buckets_from_eligible():
    deltas = [
        {"type": "footprint_delta", "bucket_ts": 0.0, "price": 100.0, "side": "buy", "delta_vol": 10.0},
        {"type": "footprint_delta", "bucket_ts": 1000.0, "price": 101.0, "side": "sell", "delta_vol": 10.0},
    ]
    gex_snapshots = [_snap(0.0, [-5.0])]  # 1000.0 시점엔 스냅샷이 max_staleness_sec(300s)보다 오래됨(STALE)
    result = build_gex_gated_signals(deltas, gex_snapshots)

    assert result["closes"] == [100.0, 101.0]
    assert result["regime_by_idx"] == ["negative", None]
    assert 1 not in result["eligible"]
