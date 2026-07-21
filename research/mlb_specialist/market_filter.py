"""MLB 마켓 식별 — 순수 휴리스틱.

Polymarket 마켓 dict(`polymarket.client._map_market` 반환)에서 MLB 경기 마켓인지
판정한다. 라이브 태그 스키마가 미확인이라 키워드 + 팀명 기반이며, 맥에서 실제
태그로 실튜닝 예정(스펙 §4). 팀명 겹침(Giants/Cardinals ↔ NFL) 오인 방지를 위해
타 리그 명시 키워드가 있으면(그리고 "mlb"/"baseball" 명시가 없으면) 제외한다.
"""
from __future__ import annotations

# MLB 30팀 닉네임(소문자). 제목/슬러그 부분매칭용.
MLB_TEAMS = {
    "yankees", "red sox", "blue jays", "rays", "orioles", "guardians", "twins",
    "white sox", "tigers", "royals", "astros", "mariners", "rangers", "angels",
    "athletics", "braves", "phillies", "mets", "marlins", "nationals", "cubs",
    "brewers", "cardinals", "reds", "pirates", "dodgers", "padres", "giants",
    "diamondbacks", "rockies",
}

# MLB로 오인하면 안 되는 타 리그/종목 키워드(팀명 겹침 방지).
_CONFLICT = (
    "nba", "nfl", "nhl", "wnba", "soccer", "football", "hockey", "basketball",
    "premier league", "ufc", "tennis", "nascar", "cricket", "lck", "esports",
)


def _text(market: dict) -> str:
    parts = [market.get("question", ""), market.get("slug", ""), market.get("event_title", "")]
    return " ".join(str(p) for p in parts).lower()


def is_mlb_market(market: dict) -> bool:
    """MLB 경기 마켓이면 True. 판정 순서:
    1) 타 리그 키워드가 있으면 → "mlb"/"baseball" 명시가 있을 때만 True, 없으면 False.
    2) "mlb"/"baseball" 명시 → True.
    3) 스포츠 마켓(sports_market_type)이면서 MLB 팀명 포함 → True.
    4) 그 외 → False(보수적)."""
    t = _text(market)
    explicit = ("mlb" in t) or ("baseball" in t)
    if any(c in t for c in _CONFLICT):
        return explicit
    if explicit:
        return True
    if market.get("sports_market_type") and any(team in t for team in MLB_TEAMS):
        return True
    return False


def mlb_condition_ids(markets: list[dict]) -> set[str]:
    """마켓 리스트에서 MLB 마켓의 condition_id 집합."""
    return {m["condition_id"] for m in markets if m.get("condition_id") and is_mlb_market(m)}
