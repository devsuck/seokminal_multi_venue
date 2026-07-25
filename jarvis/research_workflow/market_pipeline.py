"""Market Data Pipeline (P113) — 가용 시장 API 를 Research OS 로 연결한다. **읽기 전용.**

Flow: Provider → Normalization → MarketEvent → event_intelligence → Research Workflow.
지원: OHLCV·Volume·Volatility·Index·Sector. **재사용**: providers.MarketProvider + market_data_adapter.ingest
(P96) — 정규화·이벤트·연구컨텍스트가 이미 구현됨. source·timestamp·raw payload 메타데이터 보존.

원칙(문서 §Constitution, §P113): 통합·조율만. 결정적. 거래·집행·주문 없음.
"""
from __future__ import annotations


def _to_metrics(bar: dict) -> dict:
    """OHLCV/index/sector raw → market_data_adapter metrics(정규화 입력). 값 왜곡 없음."""
    b = bar or {}
    m = {}
    # 수익률: close/open 또는 명시 return
    close, open_ = b.get("close"), b.get("open")
    if b.get("return") is not None or b.get("change_pct") is not None:
        m["return"] = b.get("return", b.get("change_pct"))
    elif close is not None and open_ not in (None, 0):
        try:
            m["return"] = round((float(close) - float(open_)) / float(open_), 6)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    for k in ("volatility", "volume_ratio", "price", "close"):
        if b.get(k) is not None:
            m[k] = b[k]
    # 거래량 비율(평균 대비) 있으면 그대로, 없고 volume+avg_volume 있으면 파생
    if "volume_ratio" not in m and b.get("volume") is not None and b.get("avg_volume"):
        try:
            m["volume_ratio"] = round(float(b["volume"]) / float(b["avg_volume"]), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return m


def run(raw_bars, *, source: str = "market", assistant=None) -> dict:
    """시장 raw(OHLCV/index/sector) 배치 → MarketEvent → 연구 이벤트 + 검토 큐(읽기전용).

    source·timestamp·raw payload 메타데이터를 보존한다. 정규화/분석은 기존 어댑터가 담당.
    """
    from jarvis.research_workflow.market_data_adapter import ingest
    rows = []
    raw_meta = []
    for b in (raw_bars or []):
        item = {"asset": b.get("asset") or b.get("symbol") or b.get("instrument_id"),
                "timestamp": b.get("timestamp") or b.get("ts") or "",
                "source": b.get("source", source), "metrics": _to_metrics(b)}
        rows.append(item)
        raw_meta.append({"asset": item["asset"], "source": item["source"],
                         "timestamp": item["timestamp"], "raw_keys": sorted((b or {}).keys())})
    result = ingest(rows, source=source, assistant=assistant)
    result["raw_payload_metadata"] = raw_meta
    result["pipeline"] = "market"
    result["supported"] = ["OHLCV", "Volume", "Volatility", "Index", "Sector"]
    result["note"] = ("시장 데이터 파이프라인(읽기전용) — Provider→정규화→MarketEvent→event_intelligence→"
                      "연구워크플로. source·timestamp·raw 메타 보존. 거래·집행 없음.")
    return result
