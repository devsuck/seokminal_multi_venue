"""Data Source Adapters (P6.4) — CSV 히스토리컬 + 공개API 추상. 읽기전용·자격증명 없음."""
from __future__ import annotations

import csv
import os

from jarvis.market_data.models import MISSING, OK, PriceSnapshot, STALE, parse_ts
from jarvis.market_data.provider import MarketDataProvider

_PRICE_COLS = ("price", "close", "last")
_TS_COLS = ("timestamp", "date", "time", "ts")


class CSVHistoricalProvider(MarketDataProvider):
    """CSV(symbol, timestamp, price|OHLCV close) → 읽기전용 가격. no-lookahead·결정적.

    rows 주입 가능(테스트). stale_hours 초과 = quality STALE(여전히 반환).
    """
    source_name = "csv"

    def __init__(self, csv_path: str | None = None, rows: list[dict] | None = None,
                 stale_hours: float = 48.0) -> None:
        self.stale_hours = stale_hours
        self._by_symbol: dict[str, list] = {}
        self._invalid = 0
        raw = rows if rows is not None else self._read_csv(csv_path)
        for r in raw:
            self._ingest(r)
        # 심볼별 (dt, ts, price) 정렬(결정적)
        for sym in self._by_symbol:
            self._by_symbol[sym].sort(key=lambda x: (x[0], x[1]))

    @staticmethod
    def _read_csv(path: str | None) -> list[dict]:
        if not path or not os.path.exists(path):
            return []
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    def _ingest(self, r: dict) -> None:
        sym = r.get("symbol") or r.get("Symbol")
        ts = next((r[c] for c in _TS_COLS if c in r and r[c]), None)
        price = next((r[c] for c in _PRICE_COLS if c in r and r[c] not in (None, "")), None)
        dt = parse_ts(ts) if ts else None
        if not sym or dt is None or price is None:
            self._invalid += 1
            return
        try:
            p = float(price)
        except (TypeError, ValueError):
            self._invalid += 1
            return
        self._by_symbol.setdefault(sym, []).append((dt, str(ts), p))

    def get_price(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        series = self._by_symbol.get(symbol)
        if not series:
            return None                                  # MISSING → None
        if timestamp is None:
            dt, ts, p = series[-1]
        else:
            req = parse_ts(timestamp)
            if req is None:
                return None
            elig = [x for x in series if x[0] <= req]     # no-lookahead
            if not elig:
                return None
            dt, ts, p = elig[-1]
        quality = OK
        if timestamp is not None:
            from jarvis.market_data.models import hours_between
            age = hours_between(ts, timestamp)
            if age is not None and age > self.stale_hours:
                quality = STALE
        return PriceSnapshot(symbol=symbol, price=p, timestamp=ts, source="csv", quality=quality)

    def bars(self, symbol: str) -> list:
        """심볼 히스토리 (ts, price) — quality 평가용."""
        return [(ts, p) for _dt, ts, p in self._by_symbol.get(symbol, [])]

    def symbols(self) -> list[str]:
        return sorted(self._by_symbol)

    def health_check(self) -> dict:
        return {"status": "ok" if self._by_symbol else "empty", "provider": "CSVHistoricalProvider",
                "source": "csv", "n_symbols": len(self._by_symbol),
                "n_rows": sum(len(v) for v in self._by_symbol.values()), "invalid_rows": self._invalid}


class PublicAPIProvider(MarketDataProvider):
    """공개 API 추상(P6.4) — 자격증명/네트워크 없음. 구체 구현은 후속.

    _fetch()를 구현하면 실API 연결 가능하나, 여기선 미구현(주문능력 없음 원칙 유지).
    """
    source_name = "public_api"

    def __init__(self, base_url: str = "", stale_hours: float = 1.0) -> None:
        self.base_url = base_url
        self.stale_hours = stale_hours

    def _fetch(self, symbol: str) -> dict | None:
        raise NotImplementedError("PublicAPIProvider는 추상 — 구체 어댑터에서 _fetch 구현(자격증명 별도)")

    def get_price(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        try:
            data = self._fetch(symbol)
        except NotImplementedError:
            return None
        if not data:
            return None
        return PriceSnapshot(symbol=symbol, price=float(data["price"]),
                             timestamp=data.get("timestamp", timestamp or ""),
                             source=self.source_name, quality=OK)

    def health_check(self) -> dict:
        return {"status": "abstract", "provider": "PublicAPIProvider",
                "source": "public_api", "note": "미구현 추상(자격증명 없음)"}
