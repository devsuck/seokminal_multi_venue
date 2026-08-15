"""틱 데이터(research/data/polymarket_tick/)로 지정가 체결 시뮬레이션.

anchor 시각에 best_bid/ask로 지정가를 걸었다고 가정 — 이후 실제 체결
(price_change) 프린트가 그 가격을 뚫고 지나가면 체결로 판정한다.
틱 수집기가 sharp_wallet anchor 마켓 전체를 커버하지 않으므로(2026-08-04
전수조사: anchor 3149개 중 120개만 틱 데이터 존재) coverage=False로 구분한다.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
from pathlib import Path

_DATA_DIR = Path("research/data/polymarket_tick")


def _iter_tick_rows(date: str):
    for suffix in (".jsonl", ".jsonl.gz"):
        path = _DATA_DIR / f"{date}{suffix}"
        if path.exists():
            opener = gzip.open if suffix.endswith(".gz") else open
            with opener(path, "rt") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
            return


# date별 파일을 1회만 읽어 condition_id로 인덱싱한 캐시.
# _DATA_DIR별로 키를 나눠 테스트의 monkeypatch(_DATA_DIR 교체) 격리를 유지한다.
_INDEX_CACHE: dict[tuple[str, str], dict[str, list[dict]]] = {}


def _date_index(date: str) -> dict[str, list[dict]]:
    key = (str(_DATA_DIR), date)
    idx = _INDEX_CACHE.get(key)
    if idx is None:
        idx = {}
        for row in _iter_tick_rows(date):
            row = dict(row)
            row["_ts_epoch"] = _dt.datetime.fromisoformat(row["ts"]).timestamp()
            idx.setdefault(row.get("condition_id"), []).append(row)
        _INDEX_CACHE[key] = idx
    return idx


def load_tick_window(condition_id: str, ts_start: float, ts_end: float) -> list[dict]:
    """[ts_start, ts_end] 구간의 해당 마켓 이벤트를 ts 오름차순으로 반환(_ts_epoch 필드 추가)."""
    d0 = _dt.datetime.fromtimestamp(ts_start, tz=_dt.timezone.utc).date()
    d1 = _dt.datetime.fromtimestamp(ts_end, tz=_dt.timezone.utc).date()
    dates = {(d0 + _dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)}
    rows = []
    for date in sorted(dates):
        rows.extend(r for r in _date_index(date).get(condition_id, [])
                     if ts_start <= r["_ts_epoch"] <= ts_end)
    rows.sort(key=lambda r: r["_ts_epoch"])
    return rows


def simulate_maker_fill(condition_id: str, outcome: str, direction: float,
                         limit_price: float, ts_start: float, ts_end: float) -> dict:
    """direction>0(매수)면 limit_price 이하 체결 프린트, direction<0(매도)면
    limit_price 이상 체결 프린트를 최초로 찾아 체결로 판정.

    반환: {"filled", "fill_ts", "fill_price", "coverage"}.
    coverage=False면 구간에 틱 데이터 자체가 없어 판정 불가(=백테스트 대상 제외,
    filled=False와는 다른 상태이므로 반드시 구분해서 사용할 것).
    """
    rows = [r for r in load_tick_window(condition_id, ts_start, ts_end)
            if r.get("outcome") == outcome and r.get("event_type") == "price_change"]
    if not rows:
        return {"filled": False, "fill_ts": None, "fill_price": None, "coverage": False}
    for row in rows:
        price = row["price"]
        if (direction > 0 and price <= limit_price) or (direction < 0 and price >= limit_price):
            return {"filled": True, "fill_ts": row["_ts_epoch"], "fill_price": price, "coverage": True}
    return {"filled": False, "fill_ts": None, "fill_price": None, "coverage": True}


def _demo() -> None:
    import tempfile

    global _DATA_DIR
    orig = _DATA_DIR
    with tempfile.TemporaryDirectory() as d:
        _DATA_DIR = Path(d)
        rows = [
            {"ts": "2026-08-01T00:00:00+00:00", "condition_id": "c1", "outcome": "yes",
             "event_type": "price_change", "price": 0.50, "best_bid": 0.49, "best_ask": 0.51},
            {"ts": "2026-08-01T00:01:00+00:00", "condition_id": "c1", "outcome": "yes",
             "event_type": "price_change", "price": 0.45, "best_bid": 0.44, "best_ask": 0.46},
        ]
        (Path(d) / "2026-08-01.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

        t0 = _dt.datetime(2026, 8, 1, tzinfo=_dt.timezone.utc).timestamp()
        buy_fill = simulate_maker_fill("c1", "yes", 1.0, 0.46, t0, t0 + 300)
        assert buy_fill == {"filled": True, "fill_ts": t0 + 60, "fill_price": 0.45, "coverage": True}

        no_fill = simulate_maker_fill("c1", "yes", 1.0, 0.30, t0, t0 + 300)
        assert no_fill["filled"] is False and no_fill["coverage"] is True

        no_coverage = simulate_maker_fill("missing", "yes", 1.0, 0.30, t0, t0 + 300)
        assert no_coverage["coverage"] is False

    _DATA_DIR = orig
    print("ok")


if __name__ == "__main__":
    _demo()
