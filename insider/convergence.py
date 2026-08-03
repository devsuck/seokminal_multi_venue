"""leg별 신호를 (ticker, direction)으로 교차집계해 컨버전스 스코어를 매기는 순수 집계 레이어.
새 외부 API 호출 없음 — 기존 leg 함수를 그대로 재사용한다.
"""
from insider.dart_client import get_recent_kr_insider_feed, get_recent_kr_corporate_actions
from insider.edgar_client import get_recent_form4_feed
from insider.congress_client import get_congress_trades
from insider.options_uoa_client import get_unusual_options_activity

_DART_EXEC_DIRECTION = {"BUY": "BULLISH", "SELL": "BEARISH", "CANCELLATION": "BULLISH"}
_DART_CORP_ACTION_DIRECTION = {"BUYBACK": "BULLISH", "PAID_IN": "BEARISH", "DISPOSAL": "BEARISH"}
_US_TRADE_DIRECTION = {"BUY": "BULLISH", "SELL": "BEARISH"}
_UOA_DIRECTION = {"call": "BULLISH", "put": "BEARISH"}


def _tag_kr_legs(days: int) -> list[dict]:
    legs = []
    for row in get_recent_kr_insider_feed(days=days):
        direction = _DART_EXEC_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("stock_code"):
            continue
        legs.append({
            "source": "dart_exec",
            "ticker": row["stock_code"],
            "direction": direction,
            "trade_date": row.get("rcept_dt", ""),
            "detail": f"{row.get('corp_name', '')} {row.get('role', '')} {row.get('event_cause', '')}".strip(),
            "url": row.get("dart_url"),
        })
    for row in get_recent_kr_corporate_actions(days=days):
        direction = _DART_CORP_ACTION_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "dart_corp_action",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("trade_date", ""),
            "detail": f"{row.get('corp_name', '')} {row.get('event_cause', '')}".strip(),
            "url": row.get("dart_url"),
        })
    return legs


def _tag_us_legs_without_uoa(days: int) -> list[dict]:
    legs = []
    for row in get_recent_form4_feed(days=days):
        direction = _US_TRADE_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "form4",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("transaction_date") or row.get("filing_date", ""),
            "detail": f"{row.get('issuer', '')} Form4 {row.get('trade_type', '')}".strip(),
            "url": None,
        })
    for row in get_congress_trades(limit=80):
        direction = _US_TRADE_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "congress",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("trade_date", ""),
            "detail": f"{row.get('chamber', '')} {row.get('owner', '')}".strip(),
            "url": row.get("link"),
        })
    return legs


def _tag_uoa_legs(tickers: list[str]) -> list[dict]:
    if not tickers:
        return []
    legs = []
    for row in get_unusual_options_activity(tickers):
        direction = _UOA_DIRECTION.get(row.get("type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "options_uoa",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("expiration_date", ""),
            "detail": f"UOA {row.get('type', '')} strike={row.get('strike', '')}",
            "url": None,
        })
    return legs


def compute_convergence(market: str, days: int = 30) -> list[dict]:
    if market == "kr":
        legs = _tag_kr_legs(days)
    elif market == "us":
        legs = _tag_us_legs_without_uoa(days)
        uoa_tickers = sorted({leg["ticker"] for leg in legs})
        legs += _tag_uoa_legs(uoa_tickers)
    else:
        raise ValueError(f"unknown market: {market!r}")

    groups: dict[tuple[str, str], list[dict]] = {}
    for leg in legs:
        key = (leg["ticker"], leg["direction"])
        groups.setdefault(key, []).append(leg)

    signals = []
    for (ticker, direction), group_legs in groups.items():
        score = len({leg["source"] for leg in group_legs})
        if score < 2:
            continue
        signals.append({
            "ticker": ticker,
            "market": market,
            "direction": direction,
            "score": score,
            "legs": [{"source": l["source"], "trade_date": l["trade_date"], "detail": l["detail"], "url": l["url"]} for l in group_legs],
        })

    signals.sort(key=lambda s: s["score"], reverse=True)
    return signals
