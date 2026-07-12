"""오더플로우 컨텍스트 게이트 — 상위TF 트렌드/키레벨/VWAP 3필터(만장일치)+killzone으로
기존 오더플로우 confluence(footprint/absorption/cvd 2/3 다수결)를 게이트링.

방금 REJECT난 오더플로우 confluence 단독 가설에 실전 트레이더가 쓰는 컨텍스트 필터를
추가한 새 가설 — 컨텍스트가 방향(bias)을 정하고 오더플로우는 그 방향 안에서 타이밍만
잡는 구조. 2/3 다수결이 아니라 트렌드+키레벨+VWAP 3개 전부 일치해야 bias 성립(방향
결정은 더 보수적으로).

신규 지표 발명 없음: market_structure/swings/killzone_indices(research/ict/primitives.py)
그대로 재사용. VWAP만 신규 계산(footprint_delta가 이미 price×volume이라 신규 수집 불필요).

DORMANT 확인용 모듈. 통계적 스크리닝 목적, 실집행 근거 아님.
"""
from __future__ import annotations

from research.hypotheses.orderflow_futures import CVD_LOOKBACK_BUCKETS, SIGNAL_BUILDERS, _footprint_buckets
from research.ict.primitives import killzone_indices, market_structure, swings

KEY_LEVEL_PROXIMITY_PCT = 0.001  # 가격의 0.1% — 고정, 최적화 금지
VWAP_WINDOW_BUCKETS = 240  # 60s버킷 240개 = 4시간, 고정 — 최적화 금지


def build_ohlc_bars(ticks: list[dict], bucket_sec: float = 60.0) -> list[dict]:
    """원시 틱({ts,price,size,side}) -> bucket_sec 버킷 OHLC(틱 기준 진짜 high/low —
    footprint_delta엔 없는 정보라 여기서 별도 계산). 입력 정렬 여부 무관(내부에서 정렬)."""
    ordered = sorted(ticks, key=lambda t: t["ts"])
    bars: dict[float, dict] = {}
    order: list[float] = []
    for t in ordered:
        b = (t["ts"] // bucket_sec) * bucket_sec
        if b not in bars:
            bars[b] = {"bucket_ts": b, "o": t["price"], "h": t["price"], "l": t["price"], "c": t["price"]}
            order.append(b)
        bar = bars[b]
        bar["h"] = max(bar["h"], t["price"])
        bar["l"] = min(bar["l"], t["price"])
        bar["c"] = t["price"]
    return [bars[b] for b in order]


def resample_bars(bars: list[dict], factor: int = 15) -> list[dict]:
    """연속 factor개 바 묶어 상위 타임프레임 바 생성(o=첫바 o, h=구간 max h,
    l=구간 min l, c=마지막바 c, bucket_ts=첫바 bucket_ts). 마지막 미완성 그룹은 버림."""
    out = []
    for start in range(0, len(bars) - factor + 1, factor):
        group = bars[start:start + factor]
        out.append({
            "bucket_ts": group[0]["bucket_ts"],
            "o": group[0]["o"],
            "h": max(g["h"] for g in group),
            "l": min(g["l"] for g in group),
            "c": group[-1]["c"],
        })
    return out


def build_trend_filter(bars_15m: list[dict], k: int = 2) -> list[str]:
    """market_structure(h,l,c,k)를 15분봉에 적용. 최근 BOS/CHoCH의 dir을
    다음 이벤트 나올 때까지 forward-fill(상태 유지). 이벤트 없는 초반 구간은 HOLD."""
    h = [b["h"] for b in bars_15m]
    l = [b["l"] for b in bars_15m]
    c = [b["c"] for b in bars_15m]
    events = market_structure(h, l, c, k)
    dir_by_idx = {e["idx"]: ("BUY" if e["dir"] == "bullish" else "SELL") for e in events}

    out = []
    current = "HOLD"
    for i in range(len(bars_15m)):
        if i in dir_by_idx:
            current = dir_by_idx[i]
        out.append(current)
    return out


def build_key_level_filter(bars_15m: list[dict], proximity_pct: float = KEY_LEVEL_PROXIMITY_PCT) -> list[str]:
    """swings(h,l,k=2)로 스윙하이/로우 추출 -> 현재가가 가장 가까운 스윙레벨의
    proximity_pct 이내면 그 방향(스윙로우 근접=BUY, 스윙하이 근접=SELL)."""
    h = [b["h"] for b in bars_15m]
    l = [b["l"] for b in bars_15m]
    c = [b["c"] for b in bars_15m]
    sw = swings(h, l, k=2)
    levels = [(l[i], "BUY") for i in sw["lows"]] + [(h[i], "SELL") for i in sw["highs"]]

    out = []
    for i in range(len(bars_15m)):
        price = c[i]
        sig = "HOLD"
        if levels and price != 0:
            level_price, level_sig = min(levels, key=lambda lv: abs(lv[0] - price))
            if abs(level_price - price) / abs(price) <= proximity_pct:
                sig = level_sig
        out.append(sig)
    return out


def build_vwap_filter(deltas: list[dict], window_buckets: int = VWAP_WINDOW_BUCKETS) -> list[str]:
    """각 60s 버킷 시점 기준 직전 window_buckets 구간(그 버킷 포함) footprint_delta로
    VWAP = sum(price*vol)/sum(vol) 계산. close > VWAP -> BUY, close < VWAP -> SELL."""
    order, buy, sell, _open_price, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]
    vols = [buy.get(b, 0.0) + sell.get(b, 0.0) for b in order]

    out = []
    for i in range(len(order)):
        start = max(0, i - window_buckets + 1)
        window_closes = closes[start:i + 1]
        window_vols = vols[start:i + 1]
        total_vol = sum(window_vols)
        sig = "HOLD"
        if total_vol > 0:
            vwap = sum(p * v for p, v in zip(window_closes, window_vols)) / total_vol
            if closes[i] > vwap:
                sig = "BUY"
            elif closes[i] < vwap:
                sig = "SELL"
        out.append(sig)
    return out


def build_confluence_signals(deltas: list[dict]) -> dict:
    """footprint_imbalance/absorption/cvd_divergence 3개 다수결(2개 이상 방향 일치) ->
    그 방향, 아니면 HOLD. 세 서브신호 다 _footprint_buckets 기반이라 봉 정렬 동일.

    사전에 고정한 단일 규칙 — 결과 보고 조합 방식 바꾸지 않는다(데이터 스누핑 방지).
    eligible = cvd_divergence 판정 가능 구간(i >= CVD_LOOKBACK_BUCKETS)과 동일 —
    세 의견이 다 갖춰진 구간만 다수결 판정 자격을 준다."""
    fp = SIGNAL_BUILDERS["footprint_imbalance"](deltas)["signals"]
    ab = SIGNAL_BUILDERS["absorption"](deltas)["signals"]
    cvd_data = SIGNAL_BUILDERS["cvd_divergence"](deltas)
    cvd, closes = cvd_data["signals"], cvd_data["closes"]

    signals: list[str] = []
    eligible: list[int] = []
    for i in range(len(closes)):
        sig = "HOLD"
        if i >= CVD_LOOKBACK_BUCKETS:
            eligible.append(i)
            votes = [fp[i], ab[i], cvd[i]]
            buy_votes = votes.count("BUY")
            sell_votes = votes.count("SELL")
            if buy_votes >= 2:
                sig = "BUY"
            elif sell_votes >= 2:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


def _broadcast_15m_to_60s(bars_15m_ts: list[float], signal_15m: list[str], target_ts: list[float]) -> list[str]:
    """직전에 마감된 15분봉의 신호를 그 다음 15분봉 구간에 속한 60s 버킷들에 forward-fill로
    broadcast — 형성 중인(마감 안 된) 봉 자신의 구간에는 그 봉의 신호를 적용하지 않는다
    (룩어헤드 방지: 15분봉 신호는 그 봉의 종가로 계산되므로 봉이 마감돼야 알 수 있다).
    target_ts가 첫(마감된) 15분봉보다 이르면 HOLD."""
    out = []
    j = -1
    for ts in target_ts:
        while j + 1 < len(bars_15m_ts) and bars_15m_ts[j + 1] <= ts:
            j += 1
        out.append(signal_15m[j - 1] if j >= 1 else "HOLD")
    return out


def build_gated_confluence_signals(deltas: list[dict], ticks: list[dict]) -> dict:
    """전체 파이프라인 조립:
    1. build_ohlc_bars(ticks) -> resample_bars(15) -> trend_filter, key_level_filter (15m)
    2. build_vwap_filter(deltas) (60s)
    3. killzone_indices (60s bucket_ts)
    4. 15m 신호 -> 60s로 broadcast
    5. bias = trend/key_level/vwap 3개 전부 같은 방향이면 그 방향, 아니면 HOLD
    6. 기존 confluence(footprint/absorption/cvd 2/3 다수결) 계산
    7. bias!=HOLD and killzone 안 and confluence==bias -> 그 방향 신호, 아니면 HOLD

    eligible = bias 계산 가능했던 구간(15분봉 워밍업 지난 이후) 전체 —
    신호가 실제로 뜬 곳만이 아니라 판정 가능 모집단 전체(다른 build_*_signals와 동일 규칙)."""
    bars_1m = build_ohlc_bars(ticks, bucket_sec=60.0)
    bars_15m = resample_bars(bars_1m, factor=15)
    bars_15m_ts = [b["bucket_ts"] for b in bars_15m]

    trend_15m = build_trend_filter(bars_15m)
    key_level_15m = build_key_level_filter(bars_15m)
    vwap_60s = build_vwap_filter(deltas)

    order, _buy, _sell, _open_price, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]
    kz = set(killzone_indices([int(b) for b in order]))

    trend_60s = _broadcast_15m_to_60s(bars_15m_ts, trend_15m, order)
    key_level_60s = _broadcast_15m_to_60s(bars_15m_ts, key_level_15m, order)

    confluence = build_confluence_signals(deltas)
    conf_signals = confluence["signals"]

    signals: list[str] = []
    eligible: list[int] = []
    for i in range(len(order)):
        # 방어적 no-op: order[i]와 bars_15m_ts[0]가 같은 첫 틱에서 파생돼 실질적으로 항상
        # True다. 실제 워밍업 배제(첫 15분봉 마감 전 구간)는 이제 _broadcast_15m_to_60s가
        # 마감된 봉이 없을 때 HOLD를 반환하는 것으로 처리된다(룩어헤드 수정 이후).
        warmed_up = bool(bars_15m_ts) and order[i] >= bars_15m_ts[0]
        if warmed_up:
            eligible.append(i)

        bias = "HOLD"
        if warmed_up and trend_60s[i] == key_level_60s[i] == vwap_60s[i] and trend_60s[i] != "HOLD":
            bias = trend_60s[i]

        sig = "HOLD"
        if bias != "HOLD" and i in kz and conf_signals[i] == bias:
            sig = bias
        signals.append(sig)

    return {"closes": closes, "signals": signals, "eligible": eligible}
