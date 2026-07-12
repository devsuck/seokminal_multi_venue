from research.hypotheses.orderflow_futures import (
    build_absorption_signals,
    build_cvd_divergence_signals,
    build_footprint_imbalance_signals,
    build_iceberg_refill_signals,
    build_wall_proximity_signals,
    load_deltas,
    stop_run_events,
)


def _hd(ts, price, size):
    return {"type": "heatmap_delta", "ts": ts, "price": price, "size": size}


def _fd(bucket_ts, price, side, vol):
    return {"type": "footprint_delta", "bucket_ts": bucket_ts, "price": price, "side": side, "delta_vol": vol}


def test_load_deltas_sorts_by_bucket_ts_across_files(tmp_path):
    import json
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"
    p1.write_text(json.dumps(_fd(120.0, 100.0, "buy", 1.0)) + "\n")
    p2.write_text(json.dumps(_fd(60.0, 100.0, "buy", 1.0)) + "\n")
    result = load_deltas([str(p1), str(p2)])
    assert [d["bucket_ts"] for d in result] == [60.0, 120.0]


def test_footprint_imbalance_buy_dominant_bucket_yields_buy_signal():
    deltas = [
        _fd(0.0, 100.0, "buy", 8.0),
        _fd(0.0, 100.0, "sell", 2.0),
        _fd(60.0, 101.0, "buy", 1.0),
        _fd(60.0, 101.0, "sell", 1.0),
    ]
    result = build_footprint_imbalance_signals(deltas, imbalance_ratio=0.7)
    assert result["signals"][0] == "BUY"
    assert result["signals"][1] == "HOLD"
    assert result["closes"] == [100.0, 101.0]
    # eligible = 판정 가능(볼륨 존재) 버킷 전체 — absorption.py의 noise_floor 통과 버킷과
    # 동일 의미(신호가 실제로 뜬 버킷이 아니라 비율 계산이 가능했던 버킷)
    assert result["eligible"] == [0, 1]


def test_footprint_imbalance_sell_dominant_bucket_yields_sell_signal():
    deltas = [_fd(0.0, 100.0, "buy", 1.0), _fd(0.0, 100.0, "sell", 9.0)]
    result = build_footprint_imbalance_signals(deltas, imbalance_ratio=0.7)
    assert result["signals"][0] == "SELL"


def test_footprint_imbalance_multi_price_bucket_uses_last_arrival_price():
    # 같은 버킷에 여러 price 레벨 -> close는 마지막으로 델타 도착한 price(시간순, 리스트 순서 기준)
    deltas = [_fd(0.0, 100.0, "buy", 5.0), _fd(0.0, 101.0, "buy", 5.0)]
    result = build_footprint_imbalance_signals(deltas, imbalance_ratio=0.7)
    assert result["closes"] == [101.0]


def test_absorption_sell_dominant_but_price_holds_yields_buy():
    # 매도 우세(80%)인데 가격이 안 밀리고 오히려 오름(100->101) -> 매도 흡수 -> BUY
    deltas = [_fd(0.0, 100.0, "sell", 8.0), _fd(0.0, 101.0, "buy", 2.0)]
    result = build_absorption_signals(deltas, dominance_ratio=0.7)
    assert result["signals"][0] == "BUY"
    assert result["eligible"] == [0]


def test_absorption_buy_dominant_but_price_holds_yields_sell():
    # 매수 우세(80%)인데 가격이 안 오르고 오히려 밀림(100->99) -> 매수 흡수 -> SELL
    deltas = [_fd(0.0, 100.0, "buy", 8.0), _fd(0.0, 99.0, "sell", 2.0)]
    result = build_absorption_signals(deltas, dominance_ratio=0.7)
    assert result["signals"][0] == "SELL"


def test_absorption_sell_dominant_and_price_drops_is_hold_but_eligible():
    # 매도 우세인데 실제로 가격도 밀림(100->98) -> 흡수 아님(그냥 매도 우위) -> HOLD
    deltas = [_fd(0.0, 100.0, "sell", 8.0), _fd(0.0, 98.0, "buy", 2.0)]
    result = build_absorption_signals(deltas, dominance_ratio=0.7)
    assert result["signals"][0] == "HOLD"
    assert result["eligible"] == [0]


def test_absorption_no_dominance_is_hold():
    deltas = [_fd(0.0, 100.0, "buy", 5.0), _fd(0.0, 100.0, "sell", 5.0)]
    result = build_absorption_signals(deltas, dominance_ratio=0.7)
    assert result["signals"][0] == "HOLD"
    assert result["eligible"] == [0]


def test_cvd_divergence_price_down_cvd_up_yields_buy():
    # 누적 delta(buy-sell)는 우상향(CVD 상승)인데 가격은 하락 -> 다이버전스 -> BUY
    deltas = [
        _fd(0.0, 105.0, "buy", 1.0), _fd(0.0, 105.0, "sell", 1.0),   # cvd=0, price=105
        _fd(60.0, 104.0, "buy", 1.0), _fd(60.0, 104.0, "sell", 1.0), # cvd=0, price=104
        _fd(120.0, 103.0, "buy", 1.0), _fd(120.0, 103.0, "sell", 1.0), # cvd=0, price=103
        _fd(180.0, 102.0, "buy", 5.0),                                 # cvd=+5, price=102 (down but cvd up)
    ]
    result = build_cvd_divergence_signals(deltas, lookback_buckets=3)
    assert result["signals"][-1] == "BUY"


def test_cvd_divergence_insufficient_lookback_is_hold():
    deltas = [_fd(0.0, 100.0, "buy", 1.0)]
    result = build_cvd_divergence_signals(deltas, lookback_buckets=3)
    assert result["signals"] == ["HOLD"]
    assert result["eligible"] == []


def test_cvd_divergence_hold_bucket_with_sufficient_lookback_is_still_eligible():
    # 가격도 오르고 CVD도 올라 다이버전스가 아닌(HOLD) 버킷이라도, lookback 계산이
    # 가능했다면(i >= lookback_buckets) eligible에는 포함되어야 한다 — eligible은
    # "신호가 뜬 인덱스"가 아니라 "판정 가능 모집단"이어야 함(footprint_imbalance와 동일 의미).
    deltas = [
        _fd(0.0, 100.0, "buy", 1.0), _fd(0.0, 100.0, "sell", 1.0),    # cvd=0, price=100
        _fd(60.0, 101.0, "buy", 1.0), _fd(60.0, 101.0, "sell", 1.0),  # cvd=0, price=101
        _fd(120.0, 102.0, "buy", 1.0), _fd(120.0, 102.0, "sell", 1.0),# cvd=0, price=102
        _fd(180.0, 103.0, "buy", 5.0),                                 # cvd=+5, price=103 (up + up -> no divergence)
    ]
    result = build_cvd_divergence_signals(deltas, lookback_buckets=3)
    assert result["signals"][-1] == "HOLD"
    assert result["eligible"] == [3]


def test_wall_proximity_price_approaching_large_bid_wall_yields_buy():
    # 가격이 10에서 10.25(벽 바로 위)로 접근 -> 벽이 지지선 -> BUY
    deltas = [
        _hd(0.0, 9.75, 20.0),   # 큰 매수벽 (임계 15.0 이상)
        _hd(0.0, 10.5, 1.0),
        _hd(2.0, 9.75, 20.0),
        _hd(2.0, 10.5, 1.0),
    ]
    result = build_wall_proximity_signals(deltas, wall_size_threshold=15.0, proximity_ticks=4, tick_size=0.25)
    assert "BUY" in result["signals"]


def test_wall_proximity_no_large_wall_is_all_hold():
    deltas = [_hd(0.0, 100.0, 1.0), _hd(2.0, 100.0, 1.0)]
    result = build_wall_proximity_signals(deltas, wall_size_threshold=15.0)
    assert all(s == "HOLD" for s in result["signals"])
    assert result["eligible"] == []


def test_wall_proximity_wall_present_but_too_far_is_hold_but_eligible():
    # 벽은 존재하지만 근접 범위(proximity_ticks) 밖 -> HOLD이나 판정 가능했으므로 eligible
    # (신호가 뜬 인덱스가 아니라 "판정 가능 모집단"이 eligible이어야 함 -- footprint/CVD와 동일 규칙)
    deltas = [
        _hd(0.0, 8.0, 20.0),
        _hd(0.0, 11.0, 1.0),
    ]
    result = build_wall_proximity_signals(deltas, wall_size_threshold=15.0, proximity_ticks=4, tick_size=0.25)
    assert result["signals"] == ["HOLD"]
    assert result["eligible"] == [0]


def test_iceberg_refill_repeated_depletion_and_refill_at_same_price_yields_signal():
    # 같은 가격에서 size가 10 -> 2(소진) -> 9(즉시 재충전) 반복 -> iceberg 패턴
    deltas = [
        _hd(0.0, 100.0, 10.0),
        _hd(2.0, 100.0, 2.0),   # 80% 소진
        _hd(4.0, 100.0, 9.0),   # 재충전(refill_ratio>=0.8 of 원래)
    ]
    result = build_iceberg_refill_signals(deltas, refill_ratio=0.8, min_depletion=3.0)
    assert "BUY" in result["signals"] or "SELL" in result["signals"]


def test_iceberg_refill_gradual_decline_without_refill_is_hold():
    deltas = [_hd(0.0, 100.0, 10.0), _hd(2.0, 100.0, 8.0), _hd(4.0, 100.0, 6.0)]
    result = build_iceberg_refill_signals(deltas, refill_ratio=0.8, min_depletion=3.0)
    assert all(s == "HOLD" for s in result["signals"])


def test_iceberg_refill_flat_size_is_hold_but_eligible():
    # 같은 가격에서 사이즈가 그대로(소진/재충전 없음) -> HOLD이나 이력 3개 이상 있어
    # 판정은 가능했으므로 eligible(신호 발생 여부와 무관 -- footprint/CVD와 동일 규칙)
    deltas = [_hd(0.0, 100.0, 10.0), _hd(2.0, 100.0, 10.0), _hd(4.0, 100.0, 10.0)]
    result = build_iceberg_refill_signals(deltas, refill_ratio=0.8, min_depletion=3.0)
    assert result["signals"] == ["HOLD", "HOLD", "HOLD"]
    assert result["eligible"] == [2]


def test_stop_run_events_detects_volume_spike_after_quiet_period():
    deltas = []
    for t in range(0, 600, 60):
        deltas.append(_fd(float(t), 100.0, "buy", 1.0))
        deltas.append(_fd(float(t), 100.0, "sell", 1.0))
    # 급증: 조용한 구간(2.0/bucket) 대비 3배 이상
    deltas.append(_fd(600.0, 99.5, "sell", 10.0))
    events = stop_run_events(deltas, spike_ratio=3.0, lookback_buckets=10)
    assert len(events) == 1
    assert events[0]["side"] == "sell"
    assert events[0]["price"] == 99.5


def test_stop_run_events_empty_during_warmup():
    # 버킷 수(10) == lookback_buckets(10) -> 모든 인덱스가 i < lookback_buckets 가드에
    # 걸려 스킵됨. totals[i] >= avg * spike_ratio 비교 자체는 한 번도 실행되지 않는다
    # (아래 test_stop_run_events_empty_when_no_spike_after_warmup이 그 분기를 검증).
    deltas = [_fd(float(t), 100.0, "buy", 1.0) for t in range(0, 600, 60)]
    events = stop_run_events(deltas, spike_ratio=3.0, lookback_buckets=10)
    assert events == []


def test_stop_run_events_empty_when_no_spike_after_warmup():
    # lookback_buckets(10)보다 많은 15개 버킷을 모두 평탄한(스파이크 없는) 볼륨으로
    # 구성 -> i >= lookback_buckets인 인덱스(10~14)에서 totals[i] >= avg * spike_ratio
    # 비교가 실제로 평가되어 False가 나오는지(= 이벤트 없음) 검증한다.
    deltas = [_fd(float(t), 100.0, "buy", 1.0) for t in range(0, 900, 60)]
    assert len(deltas) == 15
    events = stop_run_events(deltas, spike_ratio=3.0, lookback_buckets=10)
    assert events == []
