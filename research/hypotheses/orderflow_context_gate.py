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
