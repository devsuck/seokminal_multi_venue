from research.hypotheses.orderflow_futures import (
    build_cvd_divergence_signals,
    build_footprint_imbalance_signals,
    load_deltas,
)


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
