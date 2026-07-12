"""가설: NQ/MNQ 오더플로우 시그널 5종 — footprint 불균형, CVD 다이버전스,
stop-run 패턴, heatmap 유동성벽 근접, iceberg refill.

⚠️ DORMANT 모듈 — 검증된 알파 아님. 임계값은 프론트(`lib/orderflow-data.ts`)와
동일 고정값 원칙(백테스트용으로 재최적화하지 않음). 입력은
`research/run_ib_orderflow_tick_collect.py`가 저장하는 footprint_delta/
heatmap_delta jsonl — 라이브 대시보드와 동일한 OrderflowAggregator 버킷팅을
거친 값이므로 원시 틱과 1:1은 아니다(footprint 60s 버킷, heatmap 2s 버킷).

이번 태스크(footprint 불균형 + CVD 다이버전스)만 구현한다. wall_proximity/
iceberg_refill/stop_run 시그널과 검증 실행기(run_hypothesis류)는 후속 태스크
범위 — YAGNI, 여기서 미리 만들지 않는다.
"""
from __future__ import annotations

import json

FOOTPRINT_IMBALANCE_RATIO = 0.7  # lib/orderflow-data.ts 흡수 판정 임계값과 동일 — 고정 파라미터, 최적화 금지
CVD_LOOKBACK_BUCKETS = 5  # 고정 파라미터, 최적화 금지


def load_deltas(paths: list[str]) -> list[dict]:
    """여러 일자 jsonl 파일 -> bucket_ts 기준 정렬된 delta 리스트."""
    deltas: list[dict] = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    deltas.append(json.loads(line))
    deltas.sort(key=lambda d: d.get("bucket_ts", d.get("ts", 0.0)))
    return deltas


def _footprint_buckets(deltas: list[dict]) -> tuple[list[float], dict[float, float], dict[float, float], dict[float, float]]:
    """footprint_delta만 골라 버킷 순서 + 버킷별 buy_vol/sell_vol 누적."""
    order: list[float] = []
    seen: set[float] = set()
    buy: dict[float, float] = {}
    sell: dict[float, float] = {}
    last_price: dict[float, float] = {}
    for d in deltas:
        if d.get("type") != "footprint_delta":
            continue
        b = d["bucket_ts"]
        if b not in seen:
            seen.add(b)
            order.append(b)
        if d["side"] == "buy":
            buy[b] = buy.get(b, 0.0) + d["delta_vol"]
        else:
            sell[b] = sell.get(b, 0.0) + d["delta_vol"]
        last_price[b] = d["price"]
    return order, buy, sell, last_price


def build_footprint_imbalance_signals(deltas: list[dict], imbalance_ratio: float = FOOTPRINT_IMBALANCE_RATIO) -> dict:
    """버킷별 buy/sell 볼륨 비율이 imbalance_ratio 넘으면 그 방향으로 BUY/SELL."""
    order, buy, sell, last_price = _footprint_buckets(deltas)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        bv, sv = buy.get(b, 0.0), sell.get(b, 0.0)
        total = bv + sv
        closes.append(last_price[b])
        sig = "HOLD"
        if total > 0:
            eligible.append(i)
            if bv / total >= imbalance_ratio:
                sig = "BUY"
            elif sv / total >= imbalance_ratio:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


def build_cvd_divergence_signals(deltas: list[dict], lookback_buckets: int = CVD_LOOKBACK_BUCKETS) -> dict:
    """누적 delta(CVD)가 lookback 구간 동안 가격과 반대 방향이면 다이버전스 신호.

    가격 하락+CVD 상승 -> BUY(매도세인 척하지만 실제 매수 우위 -> 반등 기대).
    가격 상승+CVD 하락 -> SELL. lookback 미달 버킷은 HOLD/not eligible.
    eligible은 "다이버전스가 실제로 뜬 인덱스"가 아니라 build_footprint_imbalance_signals와
    동일하게 "판정 가능했던 버킷"(i >= lookback_buckets) 전체 — HOLD로 끝난 버킷도 포함."""
    order, buy, sell, last_price = _footprint_buckets(deltas)

    cvd = 0.0
    cvd_history: list[float] = []
    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        cvd += buy.get(b, 0.0) - sell.get(b, 0.0)
        cvd_history.append(cvd)
        closes.append(last_price[b])

        sig = "HOLD"
        if i >= lookback_buckets:
            eligible.append(i)
            price_delta = closes[i] - closes[i - lookback_buckets]
            cvd_delta = cvd_history[i] - cvd_history[i - lookback_buckets]
            if price_delta < 0 and cvd_delta > 0:
                sig = "BUY"
            elif price_delta > 0 and cvd_delta < 0:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}
