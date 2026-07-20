"""HTF(15분봉) OB/iFVG 존 추적 — HL candleSnapshot REST 폴링, research.ict.primitives 재사용."""
from __future__ import annotations

import time

import requests

from research.ict.primitives import fair_value_gaps, order_blocks, swings

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
IFVG_WINDOW = 8
_INTERVAL_SEC = {"1m": 60, "15m": 900, "1h": 3600}


def fetch_htf_bars(coin: str, interval: str = "15m", bars: int = 100, timeout: float = 20.0) -> list[dict]:
    """최근 `bars`개 캔들만 REST로 받는다 — 아카이빙용 hl_candle_loader.fetch와 달리
    지속 저장 없이 라이브 폴링 전용, 매 호출 최근 구간만 재조회."""
    interval_sec = _INTERVAL_SEC[interval]
    now = int(time.time() * 1000)
    start = now - bars * interval_sec * 1000
    resp = requests.post(
        HL_INFO_URL,
        json={"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": now}},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "ts": int(c["t"] // 1000), "open": float(c["o"]), "high": float(c["h"]),
            "low": float(c["l"]), "close": float(c["c"]),
        }
        for c in data
    ]


def ifvg_zones(h: list[float], l: list[float], c: list[float], window: int = IFVG_WINDOW) -> list[dict]:
    """`primitives.ifvg_events`는 되돌림 터치 시점 idx 하나만 남기지만, 존 추적엔 FVG 원래
    가격구간(zone_lo/zone_hi)이 필요해 관통 시점(idx)에 그 구간을 존으로 되돌려준다."""
    fvgs = fair_value_gaps(h, l)
    n = len(c)
    out = []
    for f in fvgs:
        i = f["idx"]
        if f["type"] == "bearish":
            viol = next((j for j in range(i + 1, min(i + 1 + window, n)) if c[j] > f["gap_hi"]), None)
            if viol is not None:
                out.append({"idx": viol, "type": "bullish", "zone_lo": f["gap_lo"], "zone_hi": f["gap_hi"]})
        else:
            viol = next((j for j in range(i + 1, min(i + 1 + window, n)) if c[j] < f["gap_lo"]), None)
            if viol is not None:
                out.append({"idx": viol, "type": "bearish", "zone_lo": f["gap_lo"], "zone_hi": f["gap_hi"]})
    return out


class ZoneTracker:
    """OB/iFVG 존을 15분봉마다 갱신·무효화 추적. 단일 코인용, 인스턴스당 봉 히스토리 보유."""

    def __init__(self, max_bars: int = 500) -> None:
        self._max_bars = max_bars
        self._o: list[float] = []
        self._h: list[float] = []
        self._l: list[float] = []
        self._c: list[float] = []
        self._zones: dict[tuple, dict] = {}  # key=(source,type,zone_lo,zone_hi) -> record

    def update(self, bar: dict) -> None:
        self._o.append(bar["open"]); self._h.append(bar["high"])
        self._l.append(bar["low"]); self._c.append(bar["close"])
        if len(self._c) > self._max_bars:
            self._o.pop(0); self._h.pop(0); self._l.pop(0); self._c.pop(0)

        obs = order_blocks(self._o, self._h, self._l, self._c)
        ifvgs = ifvg_zones(self._h, self._l, self._c)
        new_keys = set()
        for z in obs:
            key = ("OB", z["type"], z["zone_lo"], z["zone_hi"])
            if key not in self._zones:
                new_keys.add(key)
            self._zones.setdefault(
                key, {"source": "OB", "type": z["type"], "zone_lo": z["zone_lo"], "zone_hi": z["zone_hi"], "status": "active"}
            )
        for z in ifvgs:
            key = ("iFVG", z["type"], z["zone_lo"], z["zone_hi"])
            if key not in self._zones:
                new_keys.add(key)
            self._zones.setdefault(
                key, {"source": "iFVG", "type": z["type"], "zone_lo": z["zone_lo"], "zone_hi": z["zone_hi"], "status": "active"}
            )

        latest_close = self._c[-1]
        invalidated_this_update = []
        for rec in self._zones.values():
            if rec["status"] != "active":
                continue
            if rec["type"] == "bullish" and latest_close < rec["zone_lo"]:
                rec["status"] = "invalidated"
                invalidated_this_update.append(rec)
            elif rec["type"] == "bearish" and latest_close > rec["zone_hi"]:
                rec["status"] = "invalidated"
                invalidated_this_update.append(rec)

        # 같은 봉에서 막 무효화된 존과 겹치는 신규 존은 상충 신호로 보고 함께 무효화한다.
        # (같은 종가가 한쪽 존을 깨는 동시에 그 자리를 덮는 반대쪽 신규 존을 만드는 경우,
        # 검증되지 않은 신규 존을 곧바로 활성 취급하지 않는다.)
        if invalidated_this_update and new_keys:
            for key in new_keys:
                rec = self._zones[key]
                if rec["status"] != "active":
                    continue
                for old in invalidated_this_update:
                    if rec["zone_lo"] <= old["zone_hi"] and old["zone_lo"] <= rec["zone_hi"]:
                        rec["status"] = "invalidated"
                        break

    def zone_at_price(self, price: float) -> dict | None:
        for rec in self._zones.values():
            if rec["status"] == "active" and rec["zone_lo"] <= price <= rec["zone_hi"]:
                return rec
        return None

    def mark_consumed(self, zone: dict) -> None:
        zone["status"] = "consumed"

    def next_opposing_level(self, side: str, entry_price: float) -> float | None:
        """진입가 기준 다음 반대편 유동성 레벨(HTF 스윙) — 없으면 None(목표 미확정,
        진입 스킵 신호로 쓰인다)."""
        sw = swings(self._h, self._l)
        if side == "bullish":
            candidates = [self._h[i] for i in sw["highs"] if self._h[i] > entry_price]
            return min(candidates) if candidates else None
        candidates = [self._l[i] for i in sw["lows"] if self._l[i] < entry_price]
        return max(candidates) if candidates else None
