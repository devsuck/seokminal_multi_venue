import json

import pandas as pd
import pytest

import research.hypotheses.cross_venue_skew as cvs
from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_price_series,
    build_skew_divergence,
    build_spike_signal,
    load_venue_snapshots,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_load_venue_snapshots_reads_and_sorts_by_ts(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
        {"ts": 1.0, "bids": [{"price": 98.0, "size": 2.0}], "asks": [{"price": 102.0, "size": 2.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_venue_snapshots_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 1.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    _write_jsonl(tmp_path / "binance_BTC_2026-07-13.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12", "2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_venue_snapshots_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    df = load_venue_snapshots("binance", "BTC", ["2026-01-01"])
    assert df.empty


def test_build_imbalance_neutral_when_bid_ask_equal():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 5.0}]],
        "asks": [[{"price": 101.0, "size": 5.0}]],
    })
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.5)


def test_build_imbalance_buy_heavy_above_half():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 8.0}]],
        "asks": [[{"price": 101.0, "size": 2.0}]],
    })
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.8)


def test_build_imbalance_respects_depth_n():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 1.0}, {"price": 98.0, "size": 100.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}]],
    })
    result = build_imbalance(df, depth_n=1)
    assert result.iloc[0] == pytest.approx(0.5)  # depth=1이면 size=100 레벨 무시


def test_build_imbalance_empty_book_returns_neutral():
    df = pd.DataFrame({"ts": [1.0], "bids": [[]], "asks": [[]]})
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.5)


def test_build_imbalance_index_is_ts():
    df = pd.DataFrame({
        "ts": [1.0, 2.0],
        "bids": [[{"price": 99.0, "size": 1.0}], [{"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}], [{"price": 101.0, "size": 1.0}]],
    })
    result = build_imbalance(df)
    assert list(result.index) == [1.0, 2.0]


def test_align_venues_forward_fills_within_tolerance():
    a = pd.Series([0.6, 0.7], index=[1.0, 20.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert aligned.loc[2.0, "a"] == pytest.approx(0.6)
    assert aligned.loc[4.0, "b"] == pytest.approx(0.4)  # gap=3s, 5s 이내


def test_align_venues_nan_when_gap_exceeds_tolerance():
    a = pd.Series([0.6, 0.65], index=[1.0, 20.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert pd.isna(aligned.loc[9.0, "b"])  # gap=8s, 5s 초과


def test_align_venues_columns_are_venue_names():
    a = pd.Series([0.6], index=[1.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert set(aligned.columns) == {"a", "b"}


def test_build_price_series_averages_venue_mids():
    venue_a = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}]],
    })  # mid = 100.0
    venue_b = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 98.0, "size": 1.0}]],
        "asks": [[{"price": 102.0, "size": 1.0}]],
    })  # mid = 100.0
    price = build_price_series({"a": venue_a, "b": venue_b})
    assert price.loc[1.0] == pytest.approx(100.0)


def test_build_price_series_uses_max_bid_min_ask_not_list_order():
    venue_a = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 90.0, "size": 1.0}, {"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 105.0, "size": 1.0}, {"price": 101.0, "size": 1.0}]],
    })
    price = build_price_series({"a": venue_a})
    # correct mid = (max(90,99)=99 + min(105,101)=101)/2 = 100.0
    # naive first-element mid = (90+105)/2 = 97.5 (differs, so this discriminates)
    assert price.loc[1.0] == pytest.approx(100.0)


def test_build_skew_divergence_computes_v_minus_mean_of_others():
    aligned = pd.DataFrame({"a": [0.8], "b": [0.4], "c": [0.5]}, index=[1.0])
    div = build_skew_divergence(aligned)
    assert div.loc[1.0, "a"] == pytest.approx(0.8 - (0.4 + 0.5) / 2)
    assert div.loc[1.0, "b"] == pytest.approx(0.4 - (0.8 + 0.5) / 2)


def test_build_skew_divergence_nan_when_fewer_than_two_valid():
    aligned = pd.DataFrame({"a": [0.8], "b": [float("nan")], "c": [float("nan")]}, index=[1.0])
    div = build_skew_divergence(aligned)
    assert pd.isna(div.loc[1.0, "a"])


def test_build_spike_signal_flags_above_threshold_after_warmup():
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    values = [0.0] * n + [10.0]
    divergence = pd.DataFrame({"a": values}, index=[float(i) for i in range(n + 1)])
    spikes = build_spike_signal(divergence)
    assert list(spikes["ts"]) == [float(n)]
    assert spikes.iloc[0]["venue"] == "a"
    assert spikes.iloc[0]["direction"] == 1.0


def test_build_spike_signal_no_spikes_during_warmup():
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    divergence = pd.DataFrame({"a": [float(i) for i in range(n - 1)]}, index=list(range(n - 1)))
    spikes = build_spike_signal(divergence)
    assert spikes.empty


def test_build_spike_signal_negative_direction():
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    values = [0.0] * n + [-10.0]
    divergence = pd.DataFrame({"a": values}, index=[float(i) for i in range(n + 1)])
    spikes = build_spike_signal(divergence)
    assert spikes.iloc[0]["direction"] == -1.0


def test_build_spike_signal_boundary_at_exact_threshold_and_lookback():
    """z==threshold 정확한 경계값 + lookback 경계 인덱스를 동시에 판별.
    `>=` 대신 `>`를 쓰는 버그(경계값은 fire해야 하는데 `>`면 제외됨)와
    `min_periods` off-by-one 버그(윈도우가 1칸 이르게 꽉 참, 예: min_periods=lookback-1)
    둘 다 잡아낸다.

    주의 1: rolling 윈도우(size=lookback)는 판정 대상 값 자기 자신을 마지막 원소로
    포함하므로, "목표 z"에 도달하는 입력값은 평균/표준편차가 그 값 자신에 의존하는
    자기참조 방정식이 되어 닫힌 형태로 못 구한다(단순 mean+threshold*std 공식은 성립
    안 함 — 실제로 시도해보면 z가 threshold보다 살짝 낮게 나옴). 대신 production과
    동일한 rolling mean/std(ddof=1) 계산을 그대로 사용해 이분탐색으로 z가 정확히
    threshold가 되는 입력값을 수치적으로 구한다.

    주의 2: warmup의 마지막 원소(index n-2)를 나머지(전부 0)와 다른 값(1.0)으로 둔다.
    이러면 warmup만으로 이루어진 윈도우(길이 n-1)에서 그 마지막 원소 자신의 z가
    ~sqrt(n-1)로 threshold를 훨씬 웃돌게 되어, `min_periods=lookback-1` 버그가 있을 때
    index n-2에서도 스파이크가 (부당하게) 뜬다 — 이걸로 조기 발화를 판별한다. 반대로
    올바른 구현(min_periods=lookback)에서는 index n-2 시점엔 데이터가 n-1개뿐이라
    항상 NaN이므로 warmup 값이 무엇이든 스파이크가 안 뜬다(안전).
    """
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    threshold = cvs.SPIKE_ZSCORE_THRESHOLD
    warmup = [0.0] * (n - 2) + [1.0]

    def _z_if_last(x: float) -> float:
        s = pd.Series(warmup + [x])
        m = s.rolling(window=n, min_periods=n).mean().iloc[-1]
        sd = s.rolling(window=n, min_periods=n).std().iloc[-1]
        return (x - m) / sd

    lo = sum(warmup) / len(warmup)
    assert _z_if_last(lo) < threshold
    hi = lo + 1.0
    while _z_if_last(hi) < threshold:
        hi = hi * 2 + 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _z_if_last(mid) < threshold:
            lo = mid
        else:
            hi = mid
    boundary_value = hi  # 이분탐색 수렴 지점: z(boundary_value) == threshold (bit-precise)
    assert _z_if_last(boundary_value) == pytest.approx(threshold, abs=1e-9)

    values = warmup + [boundary_value]
    divergence = pd.DataFrame({"a": values}, index=[float(i) for i in range(n)])
    spikes = build_spike_signal(divergence)
    # 정확히 index n-1(첫 풀윈도우 인덱스)에서만 fire — 더 이르면(n-2 포함, lookback
    # off-by-one) 리스트에 항목이 더 생겨서 실패하고, 아예 안 뜨면(>= 대신 > 버그)
    # 리스트가 비어서 실패한다.
    assert list(spikes["ts"]) == [float(n - 1)]
