"""대상 마켓 선정 — 순수함수, I/O 없음."""
from __future__ import annotations

import datetime as dt

MIN_LIQUIDITY = 5000.0  # polymarket_arb/collector.py의 MIN_LIQUIDITY와 같은 값(복제, import 금지)
SPORTS_WINDOW_BEFORE = dt.timedelta(minutes=30)
SPORTS_WINDOW_AFTER = dt.timedelta(hours=4)
NEWS_MAX_DAYS_TO_RESOLUTION = 3


def _parse_game_start(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace(" ", "T"))
    except ValueError:
        return None


def _classify(market: dict, now: dt.datetime) -> str | None:
    if market["liquidity"] < MIN_LIQUIDITY:
        return None
    if market.get("sports_market_type"):
        start = _parse_game_start(market.get("game_start_time"))
        if start is None:
            return None
        if now - SPORTS_WINDOW_BEFORE <= start <= now + SPORTS_WINDOW_AFTER:
            return "sports"
        return None
    try:
        end = dt.date.fromisoformat(market["end_date"])
    except ValueError:
        return None
    if (end - now.date()).days < NEWS_MAX_DAYS_TO_RESOLUTION:
        return "news"
    return None


def select_target_markets(markets: list[dict], now: dt.datetime) -> list[dict]:
    """수집 대상 마켓 선정. 유동성 하한 미달, 스포츠 경기시간 범위 밖,
    뉴스 잔여기간 조건 미충족은 제외. 통과한 마켓엔 family 키를 추가한다."""
    out = []
    for m in markets:
        family = _classify(m, now)
        if family is None:
            continue
        out.append({**m, "family": family})
    return out


def build_meta_by_token(markets: list[dict]) -> dict[str, dict]:
    """select_target_markets() 출력에서 token_id -> 메타 매핑을 만든다."""
    meta: dict[str, dict] = {}
    for m in markets:
        yes_id, no_id = m["clob_token_ids"]
        for token_id, outcome in ((yes_id, "yes"), (no_id, "no")):
            if token_id:
                meta[token_id] = {
                    "condition_id": m["condition_id"],
                    "question": m["question"],
                    "family": m["family"],
                    "outcome": outcome,
                }
    return meta
