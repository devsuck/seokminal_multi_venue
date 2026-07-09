"""가격×시간 버킷 롤링 집계 — 풋프린트(체결량) + 히트맵(잔량). 메모리 내 윈도우만 유지."""
import math

from orderflow.models import FootprintCell, HeatmapCell, OrderBookSnapshot, TradeEvent


class OrderflowAggregator:
    def __init__(
        self,
        tick_size: float = 1.0,
        footprint_bucket_sec: float = 60.0,
        heatmap_bucket_sec: float = 2.0,
        max_window_sec: float = 7200.0,
    ) -> None:
        self._tick_size = tick_size
        self._footprint_bucket_sec = footprint_bucket_sec
        self._heatmap_bucket_sec = heatmap_bucket_sec
        self._max_window_sec = max_window_sec
        self._footprint: dict[tuple[float, float], FootprintCell] = {}
        self._heatmap: dict[tuple[float, float], HeatmapCell] = {}

    def _round_price(self, price: float) -> float:
        return math.floor(price / self._tick_size) * self._tick_size

    def _bucket(self, ts: float, bucket_sec: float) -> float:
        return math.floor(ts / bucket_sec) * bucket_sec

    def _prune(self, buckets: dict[tuple[float, float], object], latest_bucket_ts: float) -> None:
        cutoff = latest_bucket_ts - self._max_window_sec
        stale = [key for key in buckets if key[0] < cutoff]
        for key in stale:
            del buckets[key]

    def on_trade(self, trade: TradeEvent) -> dict:
        price = self._round_price(trade.price)
        bucket_ts = self._bucket(trade.ts, self._footprint_bucket_sec)
        key = (bucket_ts, price)
        cell = self._footprint.get(key)
        if cell is None:
            cell = FootprintCell(bucket_ts=bucket_ts, price=price, buy_vol=0.0, sell_vol=0.0)
            self._footprint[key] = cell
        if trade.side == "buy":
            cell.buy_vol += trade.size
        else:
            cell.sell_vol += trade.size
        self._prune(self._footprint, bucket_ts)
        return {
            "type": "footprint_delta",
            "bucket_ts": bucket_ts,
            "price": price,
            "side": trade.side,
            "delta_vol": trade.size,
        }

    def on_book_snapshot(self, book: OrderBookSnapshot) -> list[dict]:
        bucket_ts = self._bucket(book.ts, self._heatmap_bucket_sec)
        deltas = []
        for level in (*book.bids, *book.asks):
            price = self._round_price(level.price)
            key = (bucket_ts, price)
            self._heatmap[key] = HeatmapCell(ts=bucket_ts, price=price, size=level.size)
            deltas.append({"type": "heatmap_delta", "ts": bucket_ts, "price": price, "size": level.size})
        self._prune(self._heatmap, bucket_ts)
        return deltas

    def snapshot(self) -> dict:
        return {
            "footprint": [c.model_dump() for c in self._footprint.values()],
            "heatmap": [c.model_dump() for c in self._heatmap.values()],
        }
