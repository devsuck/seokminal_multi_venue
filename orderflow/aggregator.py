"""가격×시간 버킷 롤링 집계 — 풋프린트(체결량) + 히트맵(잔량). 메모리 내 윈도우만 유지."""
import math
import statistics

from orderflow.models import FootprintCell, HeatmapCell, OrderBookSnapshot, TradeEvent

MAX_LEVELS_PER_SIDE = 25

# 체결속도(Speed of Tape) 롤링 윈도우 — 짧을수록 순간 버스트에 민감, 길수록 완만.
# 10s는 딥차트 등 유사 툴의 관례적 창 크기 참고, 결과 보고 튜닝하지 않는다.
TAPE_WINDOW_SEC = 10.0

# 스푸핑 의심 휴리스틱(frozen, 결과 보고 튜닝 안 함) — 주의: 우리 데이터는 L2 스냅샷(가격×잔량)뿐이고
# 거래소 order-id/추가·취소·정정 이벤트가 없다. 따라서 이건 "레이어링하는 실제 주체"를 식별하는 게
# 아니라 "그 자리 잔량이 큰 채로 잠깐 있다가 체결 없이 사라졌다"는 패턴 매칭일 뿐이다. 정상적인
# 유동성 인출, 상위 25단계 depth 밖으로 가격이 밀려난 경우도 동일 패턴을 만들 수 있어 오탐이 난다.
# 프론트/알림에 반드시 "낮은 신뢰도" 라벨과 함께 노출해야 한다.
SPOOF_SIZE_MULTIPLIER = 5.0  # 같은 스냅샷의 같은 사이드 중앙값 대비 몇 배 이상이어야 "크다"로 볼지
SPOOF_MAX_LIFETIME_SEC = 3.0  # 이 시간 안에 사라지거나 축소돼야 "빠르게 뺐다"로 볼지
SPOOF_TRADE_LOOKBACK_SEC = 30.0  # 체결기록 대조용 보존 윈도우(수명 판정창보다 여유있게)


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
        self._recent_trade_ts: list[float] = []
        self._recent_trade_prices: list[tuple[float, float]] = []  # (ts, price) — 스푸핑 체결대조용
        self._spoof_watch: dict[tuple[str, float], dict] = {}  # (side, price) -> {peak_size, first_ts}

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

    def _tape_speed(self, ts: float) -> float:
        """최근 TAPE_WINDOW_SEC초 체결건수/초 — 체결이 뜸해지면(창 내 1건뿐이어도) 다음 체결이
        올 때까지 값이 안 내려가는 한계 있음(폴링이 아니라 이벤트 트리거라 무체결 구간을 못 앎).
        실시간 "지금 얼마나 빠른가" 근사치일 뿐, 정밀 계측기 아님."""
        self._recent_trade_ts.append(ts)
        cutoff = ts - TAPE_WINDOW_SEC
        self._recent_trade_ts = [t for t in self._recent_trade_ts if t >= cutoff]
        return len(self._recent_trade_ts) / TAPE_WINDOW_SEC

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
        tape_trades_per_sec = self._tape_speed(trade.ts)
        self._recent_trade_prices.append((trade.ts, price))
        cutoff = trade.ts - SPOOF_TRADE_LOOKBACK_SEC
        self._recent_trade_prices = [(t, p) for t, p in self._recent_trade_prices if t >= cutoff]
        return {
            "type": "footprint_delta",
            "bucket_ts": bucket_ts,
            "price": price,
            "side": trade.side,
            "delta_vol": trade.size,
            "tape_trades_per_sec": tape_trades_per_sec,
        }

    def _traded_at_price_between(self, price: float, start_ts: float, end_ts: float) -> bool:
        return any(price == p and start_ts <= t <= end_ts for t, p in self._recent_trade_prices)

    def _check_spoof_watch(self, side: str, levels: list, median_size: float, ts: float) -> list[dict]:
        """levels(해당 사이드 상위 N단계)를 훑어 큰 잔량이 짧게 나타났다 체결 없이 사라진 패턴을 찾는다.
        order-id 기반 진짜 스푸핑 탐지가 아니라 스냅샷 패턴 매칭 휴리스틱 — 호출부에서 낮은 신뢰도로 표기할 것."""
        alerts: list[dict] = []
        current: dict[float, float] = {}
        for level in levels:
            price = self._round_price(level.price)
            current[price] = level.size
            key = (side, price)
            watch = self._spoof_watch.get(key)
            is_large = median_size > 0 and level.size >= SPOOF_SIZE_MULTIPLIER * median_size
            if is_large:
                if watch is None:
                    self._spoof_watch[key] = {"peak_size": level.size, "first_ts": ts}
                else:
                    watch["peak_size"] = max(watch["peak_size"], level.size)
            elif watch is not None:
                alerts.extend(self._resolve_spoof_watch(side, price, watch, ts))
                del self._spoof_watch[key]

        for key in [k for k in self._spoof_watch if k[0] == side and k[1] not in current]:
            watch = self._spoof_watch.pop(key)
            alerts.extend(self._resolve_spoof_watch(side, key[1], watch, ts))
        return alerts

    def _resolve_spoof_watch(self, side: str, price: float, watch: dict, ts: float) -> list[dict]:
        lifetime = ts - watch["first_ts"]
        if lifetime > SPOOF_MAX_LIFETIME_SEC:
            return []
        if self._traded_at_price_between(price, watch["first_ts"], ts):
            return []  # 실제 체결로 소진된 물량 — 스푸핑 후보 아님
        return [
            {
                "type": "spoof_alert",
                "ts": ts,
                "side": side,
                "price": price,
                "peak_size": watch["peak_size"],
                "lifetime_sec": round(lifetime, 2),
                "confidence": "low",
                "note": "휴리스틱: 큰 잔량이 짧게 나타났다 체결 없이 사라짐. order-id 기반 진짜 스푸핑 탐지 아님(L2 스냅샷만 사용) — 참고용 신호.",
            }
        ]

    def on_book_snapshot(self, book: OrderBookSnapshot) -> list[dict]:
        bucket_ts = self._bucket(book.ts, self._heatmap_bucket_sec)
        self._heatmap_latest_bucket_ts = bucket_ts
        deltas = []
        # 거래소가 보내는 원장 뎁스가 얼마든 상관없이 스냅샷 크기를 예측 가능하게 유지 —
        # 히트맵은 터치 근처 유동성만 보면 되고, 먼 호가까지 다 저장할 이유 없다
        bids = book.bids[:MAX_LEVELS_PER_SIDE]
        asks = book.asks[:MAX_LEVELS_PER_SIDE]
        near_touch = (*bids, *asks)
        for level in near_touch:
            price = self._round_price(level.price)
            key = (bucket_ts, price)
            existing = self._heatmap.get(key)
            if existing is not None and existing.size == level.size:
                continue
            self._heatmap[key] = HeatmapCell(ts=bucket_ts, price=price, size=level.size)
            deltas.append({"type": "heatmap_delta", "ts": bucket_ts, "price": price, "size": level.size})
        self._prune(self._heatmap, bucket_ts, self._heatmap_max_window_sec)

        bid_median = statistics.median([lvl.size for lvl in bids]) if bids else 0.0
        ask_median = statistics.median([lvl.size for lvl in asks]) if asks else 0.0
        deltas.extend(self._check_spoof_watch("bid", bids, bid_median, book.ts))
        deltas.extend(self._check_spoof_watch("ask", asks, ask_median, book.ts))
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
