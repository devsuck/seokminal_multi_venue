"""가격×시간 버킷 롤링 집계 — 풋프린트(체결량) + 히트맵(잔량). 메모리 내 윈도우만 유지."""
import math

from orderflow.models import FootprintCell, HeatmapCell, OrderBookSnapshot, TradeEvent

MAX_LEVELS_PER_SIDE = 25


class OrderflowAggregator:
    def __init__(
        self,
        tick_size: float = 1.0,
        footprint_bucket_sec: float = 60.0,
        heatmap_bucket_sec: float = 2.0,
        max_window_sec: float = 7200.0,
        # 서버 내부 보존 윈도우(메모리 상한, on_book_snapshot마다 _prune)와 신규 접속자에게
        # 보내는 초기 snapshot() 페이로드 크기는 별개 문제라 분리한다.
        # - heatmap_max_window_sec: 얼마나 오래 들고 있을지. 이미 붙어있는 클라는 이 값과
        #   무관하게 delta 스트림으로 계속 누적하므로, 길게 잡아도 스냅샷 크기엔 영향 없다.
        # - heatmap_snapshot_window_sec: 신규 접속자 snapshot()에 실제로 담기는 최근 구간.
        #   실측(2026-07-12, BTC.HL): 300s(150버킷×~125가격)=6152셀=페이로드 340KB,
        #   600s는 선형 ~680KB. 1MB WS 메시지 한도 내 안전마진 확보 위해 600s 고정.
        heatmap_max_window_sec: float = 5400.0,  # 90분 — 기본 차트 가시 범위만큼 실시간 누적
        heatmap_snapshot_window_sec: float = 600.0,
    ) -> None:
        self._tick_size = tick_size
        self._footprint_bucket_sec = footprint_bucket_sec
        self._heatmap_bucket_sec = heatmap_bucket_sec
        self._max_window_sec = max_window_sec
        self._heatmap_max_window_sec = heatmap_max_window_sec
        self._heatmap_snapshot_window_sec = heatmap_snapshot_window_sec
        self._footprint: dict[tuple[float, float], FootprintCell] = {}
        self._heatmap: dict[tuple[float, float], HeatmapCell] = {}
        self._heatmap_latest_bucket_ts = 0.0

    def _round_price(self, price: float) -> float:
        return round(math.floor(price / self._tick_size + 1e-9) * self._tick_size, 8)

    def _bucket(self, ts: float, bucket_sec: float) -> float:
        return math.floor(ts / bucket_sec) * bucket_sec

    def _prune(
        self, buckets: dict[tuple[float, float], object], latest_bucket_ts: float, window_sec: float
    ) -> None:
        cutoff = latest_bucket_ts - window_sec
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
        self._prune(self._footprint, bucket_ts, self._max_window_sec)
        return {
            "type": "footprint_delta",
            "bucket_ts": bucket_ts,
            "price": price,
            "side": trade.side,
            "delta_vol": trade.size,
        }

    def on_book_snapshot(self, book: OrderBookSnapshot) -> list[dict]:
        bucket_ts = self._bucket(book.ts, self._heatmap_bucket_sec)
        self._heatmap_latest_bucket_ts = bucket_ts
        deltas = []
        # 거래소가 보내는 원장 뎁스가 얼마든 상관없이 스냅샷 크기를 예측 가능하게 유지 —
        # 히트맵은 터치 근처 유동성만 보면 되고, 먼 호가까지 다 저장할 이유 없다
        near_touch = (*book.bids[:MAX_LEVELS_PER_SIDE], *book.asks[:MAX_LEVELS_PER_SIDE])
        for level in near_touch:
            price = self._round_price(level.price)
            key = (bucket_ts, price)
            existing = self._heatmap.get(key)
            if existing is not None and existing.size == level.size:
                continue
            self._heatmap[key] = HeatmapCell(ts=bucket_ts, price=price, size=level.size)
            deltas.append({"type": "heatmap_delta", "ts": bucket_ts, "price": price, "size": level.size})
        self._prune(self._heatmap, bucket_ts, self._heatmap_max_window_sec)
        return deltas

    def latest_book(self, book: OrderBookSnapshot, levels: int = 20) -> dict:
        bids = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)[:levels]
        asks = sorted(book.asks, key=lambda lvl: lvl.price)[:levels]
        return {
            "type": "book_snapshot",
            "bids": [{"price": lvl.price, "size": lvl.size} for lvl in bids],
            "asks": [{"price": lvl.price, "size": lvl.size} for lvl in asks],
            "venues": book.venues,
        }

    def snapshot(self) -> dict:
        heatmap_cutoff = self._heatmap_latest_bucket_ts - self._heatmap_snapshot_window_sec
        return {
            "footprint": [c.model_dump() for c in self._footprint.values()],
            "heatmap": [c.model_dump() for c in self._heatmap.values() if c.ts >= heatmap_cutoff],
        }
