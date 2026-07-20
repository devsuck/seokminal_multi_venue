"""LTF(1분) 봉 빌더 + 반전형 오더플로우 트리거(흡수/스탑런/다이버전스) 라이브 감지.
프론트(lib/orderflow-data.ts: detectAbsorption/detectStopRuns/detectDeltaDivergence)와
동일 임계값 — 대시보드와 다른 신호를 보면 안 되므로 값만 이식하고 튜닝하지 않는다."""
from __future__ import annotations

from collections import deque
from typing import Literal

from orderflow.models import TradeEvent

ROLLING_WINDOW = 200
ABSORPTION_DOMINANCE_RATIO = 0.7
ABSORPTION_NOISE_FLOOR_MULTIPLIER = 10.0
STOP_RUN_LOOKBACK_BARS = 20
STOP_RUN_NOISE_FLOOR_MULTIPLIER = 10.0
DIVERGENCE_LOOKBACK_BARS = 20
DIVERGENCE_MIN_DELTA_RATIO = 0.25
MAX_BARS_KEPT = 200

Side = Literal["buy", "sell"]


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2.0 if n % 2 == 0 else s[mid]


def check_absorption(bar: dict, buy_vol: float, sell_vol: float, rolling_median: float) -> Side | None:
    """`lib/orderflow-data.ts::detectAbsorption`과 동일 규칙."""
    if rolling_median <= 0:
        return None
    total = buy_vol + sell_vol
    noise_floor = rolling_median * ABSORPTION_NOISE_FLOOR_MULTIPLIER
    if total < noise_floor:
        return None
    sell_ratio = sell_vol / total
    buy_ratio = buy_vol / total
    if sell_ratio >= ABSORPTION_DOMINANCE_RATIO and bar["close"] >= bar["open"]:
        return "buy"  # 매도 우세인데 안 밀림 = 매도 흡수 = 강세
    if buy_ratio >= ABSORPTION_DOMINANCE_RATIO and bar["close"] <= bar["open"]:
        return "sell"
    return None


def check_stop_run(bar: dict, recent_bars: list[dict], total_vol: float, rolling_median: float) -> Side | None:
    """`lib/orderflow-data.ts::detectStopRuns`와 동일 규칙. recent_bars = 직전 20봉(현재봉 제외)."""
    if rolling_median <= 0 or len(recent_bars) < STOP_RUN_LOOKBACK_BARS:
        return None
    noise_floor = rolling_median * STOP_RUN_NOISE_FLOOR_MULTIPLIER
    if total_vol < noise_floor:
        return None
    window = recent_bars[-STOP_RUN_LOOKBACK_BARS:]
    recent_high = max(b["high"] for b in window)
    recent_low = min(b["low"] for b in window)
    if bar["high"] > recent_high and bar["close"] < recent_high:
        return "sell"
    if bar["low"] < recent_low and bar["close"] > recent_low:
        return "buy"
    return None


def check_divergence(bar: dict, recent_bars: list[dict], net_delta: float, total_vol: float) -> Side | None:
    """`lib/orderflow-data.ts::detectDeltaDivergence`와 동일 규칙."""
    if len(recent_bars) < DIVERGENCE_LOOKBACK_BARS or total_vol <= 0:
        return None
    if abs(net_delta) < total_vol * DIVERGENCE_MIN_DELTA_RATIO:
        return None
    window = recent_bars[-DIVERGENCE_LOOKBACK_BARS:]
    recent_high = max(b["high"] for b in window)
    recent_low = min(b["low"] for b in window)
    if bar["high"] > recent_high and net_delta < 0:
        return "sell"
    if bar["low"] < recent_low and net_delta > 0:
        return "buy"
    return None


def _classify(
    bar: dict, recent_bars: list[dict], buy_vol: float, sell_vol: float, rolling_median: float
) -> tuple[str | None, Side | None]:
    side = check_absorption(bar, buy_vol, sell_vol, rolling_median)
    if side is not None:
        return "absorption", side
    total_vol = buy_vol + sell_vol
    side = check_stop_run(bar, recent_bars, total_vol, rolling_median)
    if side is not None:
        return "stop_run", side
    side = check_divergence(bar, recent_bars, buy_vol - sell_vol, total_vol)
    if side is not None:
        return "divergence", side
    return None, None


class LTFBarBuilder:
    """1분 트레이드를 봉으로 집계, 봉 마감마다 반전형 트리거 판정까지 함께 반환."""

    def __init__(self, bucket_sec: float = 60.0) -> None:
        self._bucket_sec = bucket_sec
        self._cur_bucket: int | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._buy_vol = 0.0
        self._sell_vol = 0.0
        self._recent_sizes: deque[float] = deque(maxlen=ROLLING_WINDOW)
        self.bars: list[dict] = []

    def on_trade(self, trade: TradeEvent) -> dict | None:
        bucket = int(trade.ts // self._bucket_sec)
        finalized: dict | None = None
        if self._cur_bucket is None:
            self._cur_bucket = bucket
            self._o = self._h = self._l = self._c = trade.price
            self._buy_vol = 0.0
            self._sell_vol = 0.0
        elif bucket != self._cur_bucket:
            finalized = self._finalize()
            self._cur_bucket = bucket
            self._o = self._h = self._l = self._c = trade.price
            self._buy_vol = 0.0
            self._sell_vol = 0.0

        self._h = max(self._h, trade.price)
        self._l = min(self._l, trade.price)
        self._c = trade.price
        if trade.side == "buy":
            self._buy_vol += trade.size
        else:
            self._sell_vol += trade.size
        self._recent_sizes.append(trade.size)
        return finalized

    def _finalize(self) -> dict:
        bar = {
            "ts": self._cur_bucket * self._bucket_sec,
            "open": self._o, "high": self._h, "low": self._l, "close": self._c,
        }
        rolling_median = _median(list(self._recent_sizes))
        recent_bars = self.bars[-MAX_BARS_KEPT:]
        trigger_name, side = _classify(bar, recent_bars, self._buy_vol, self._sell_vol, rolling_median)

        self.bars.append(bar)
        if len(self.bars) > MAX_BARS_KEPT:
            self.bars.pop(0)

        return {"bar": bar, "of_trigger": trigger_name, "side": side}
