"""크립토 초단기(5분/15분) up/down 마켓 선정 — 차익 재검증 전용.

일반 마켓 스캔(`collector.py::select_liquid_markets`)은 `MIN_DAYS_TO_RESOLUTION=3`
플로어 때문에 `{coin}-updown-{5m|15m}-{unix_ts}` 슬러그의 초단기 마켓을 전부
걸러낸다. 이 모듈은 그 마켓들만 마감임박 기준으로 별도로 골라내는 순수함수다 —
오더북 조회/차익 판정(`collector.py::snapshot_market`, `detector.py::evaluate_snapshot`)은
전혀 새로 안 만들고 그대로 재사용한다.
"""
from __future__ import annotations

import datetime as dt
import re

_SLUG_RE = re.compile(r"^[a-z0-9]+-updown-\d+(m|h)-\d+$")

# 일반 MIN_LIQUIDITY=5000(collector.py)와 다른 값 — 개설 초기 up/down 마켓은
# 유동성이 훨씬 낮게 관측됨(24h 전 시점 ~1000 수준). 표본 더 쌓이면 조정할
# 미검증 근사치.
MIN_LIQUIDITY = 500.0
MAX_MINUTES_TO_RESOLVE = 15.0


def _parse_end_datetime(raw: str) -> dt.datetime | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def select_updown_markets(
    markets: list[dict],
    *,
    now: dt.datetime | None = None,
    max_minutes_to_resolve: float = MAX_MINUTES_TO_RESOLVE,
    min_liquidity: float = MIN_LIQUIDITY,
) -> list[dict]:
    """마감임박(0 <= 남은분 <= max_minutes_to_resolve) + 슬러그패턴 일치 +
    최소유동성 이상 + 오더북 조회 가능한 up/down 마켓만, 유동성 내림차순으로."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    out = []
    for m in markets:
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            continue
        if m.get("clob_token_ids") in (None, (None, None)):
            continue
        if m["liquidity"] < min_liquidity:
            continue
        if not _SLUG_RE.match(m.get("slug") or ""):
            continue
        end_dt = _parse_end_datetime(m.get("end_datetime") or "")
        if end_dt is None:
            continue
        minutes_left = (end_dt - now).total_seconds() / 60.0
        if not (0.0 <= minutes_left <= max_minutes_to_resolve):
            continue
        out.append(m)
    out.sort(key=lambda x: x["liquidity"], reverse=True)
    return out
